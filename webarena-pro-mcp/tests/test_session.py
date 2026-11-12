import asyncio
import base64
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mcp.types import CallToolResult
from webarena_pro_mcp.artifacts import Artifacts
from webarena_pro_mcp.evaluation import ScoreBook
from webarena_pro_mcp.mcp_client import MCPBrowser
from webarena_pro_mcp.media_policy import MediaSettings, schemas
from webarena_pro_mcp.tool_policy import ToolPolicy

from webarena_pro_mcp.session import Session, message
from webarena_pro_mcp.tool_policy import PolicyError


@pytest.fixture
def episode(tmp_path, monkeypatch):
    browser = SimpleNamespace(
        tools=[
            {
                "name": "browser_snapshot",
                "description": "Snapshot",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                }
            }
        ],
        call=AsyncMock(return_value=message("Ready")),
        current_url=AsyncMock(return_value="http://fixture/"),
    )
    browser.tools.extend([
        {"name": name, "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}
        for name in ("browser_click", "browser_take_screenshot", "browser_find", "media_extract_frames")
    ])
    supervisor = SimpleNamespace(call=AsyncMock(return_value={}))

    async def grade(*args, **kwargs):
        answer = args[3]
        score = float(answer == "send_msg_to_user('42')")
        return {"score": score, "success": score == 1, "dag_results": {}}, message("Private")

    monkeypatch.setattr("webarena_pro_mcp.session.grade", grade)
    return Session(
        browser,
        supervisor,
        Artifacts(tmp_path / "evidence"),
        {
            "max_steps": 50,
            "wall_seconds": 100,
            "tool_timeout": 1,
            "evaluation_timeout": 1,
            "media": {"timeout": 1},
        },
    )


async def test_submit_is_terminal_and_no_reward_leaks(episode):
    result = await episode.call("webarena_submit", {"answer": "42"})
    assert not result["isError"]
    assert "reward" not in json.dumps(result)
    assert (await episode.call("browser_snapshot", {}))["isError"]
    final = await episode.finalize()
    assert final["rewards"] == {"reward": 1, "success": 1, "score_at_50": 1}
    assert final["steps"] == 0
    assert await episode.finalize() is final


async def test_concurrency_cannot_bypass_budget(episode):
    results = await asyncio.gather(*(episode.call("browser_click", {}) for _ in range(55)))
    assert sum(not r["isError"] for r in results) == 50
    assert episode.steps == 50
    assert episode.browser.call.await_count == 50
    assert "50" not in episode.book.scores
    assert (await episode.finalize())["rewards"]["score_at_50"] == 0


async def test_invalid_tools_and_arguments_never_dispatch(episode):
    assert (await episode.call("browser_evaluate", {"function": "fetch('/api/eval')"}))["isError"]
    assert (await episode.call("browser_snapshot", {"filename": "/etc/passwd"}))["isError"]
    assert episode.browser.call.await_count == 0
    assert episode.steps == 0


async def test_observations_and_rejected_actions_leave_full_ui_budget(episode):
    for name in ("browser_snapshot", "browser_take_screenshot", "browser_find"):
        assert not (await episode.call(name, {}))["isError"]
    episode.browser.call.side_effect = PolicyError("Use a reference from the latest browser observation")
    assert (await episode.call("browser_click", {}))["isError"]
    episode.browser.call.side_effect = None
    episode.browser.call.return_value = {**message("Stale reference", error=True), "rejected_before_action": True}
    assert (await episode.call("browser_click", {}))["isError"]
    assert episode.steps == 0
    episode.browser.call.return_value = message("Action timed out after dispatch", error=True)
    assert (await episode.call("browser_click", {}))["isError"]
    assert episode.steps == 1  # A possibly partial action is still charged.


async def test_cutoff_is_not_repeated_by_observations_and_submit_is_regraded(episode, monkeypatch):
    episode.config["max_steps"] = -1
    episode.book = ScoreBook(-1)
    episode.steps = 49
    grader = AsyncMock(side_effect=[
        ({"score": 0, "success": False}, message("Private")),
        ({"score": 1, "success": True}, message("Private")),
    ])
    monkeypatch.setattr("webarena_pro_mcp.session.grade", grader)
    await episode.call("browser_click", {})
    assert grader.await_count == 1
    await episode.call("browser_snapshot", {})
    await episode.call("browser_take_screenshot", {})
    await episode.call("webarena_submit", {"answer": "42"})
    assert grader.await_count == 1
    final = await episode.finalize()
    assert grader.await_count == 2
    assert final["steps"] == 50 and final["score"] == 1
    assert final["step_budget_scores"]["50"]["score"] == 1
    assert final["step_budget_scores"]["100"]["score"] == 1
    assert final["step_budget_scores"]["unlimited"]["score"] == 1


async def test_trajectory_urls_and_stated_rationale_reach_shared_judge(episode):
    from webarena_pro_core.eval.dag import EvalContext
    from webarena_pro_core.eval.llm_judge import build_judge_messages

    for name in ("browser_click", "browser_take_screenshot", "media_extract_frames"):
        result = await episode.call(name, {"webarena_rationale": f"Check the result of {name}"})
        assert not result["isError"]
        episode.browser.call.assert_awaited_with(name, {})
    await episode.call("webarena_submit", {"answer": "42", "webarena_rationale": "The requested work is complete."})
    assert {s["obs"]["url"] for s in episode.trajectory} == {"http://fixture/"}
    context = EvalContext(trajectory=episode.trajectory, task_config={"intent": "Save the result"})
    prompts = json.dumps(build_judge_messages("Result is saved", context))
    assert "URL: http://fixture/" in prompts
    assert "Reasoning: Check the result of browser_click" in prompts
    assert "Reasoning: The requested work is complete." in prompts
    assert "webarena_rationale" not in episode.trajectory[-1]["action"]
    persisted = [json.loads(line) for line in (episode.artifacts.root / "trajectory.jsonl").read_text().splitlines()]
    assert persisted == episode.trajectory


async def test_missing_rationale_is_not_invented_and_bad_metadata_is_rejected(episode):
    for rationale in (None, {}, "x" * 10001):
        assert (await episode.call("browser_click", {"webarena_rationale": rationale}))["isError"]
    episode.browser.call.assert_not_awaited()
    assert episode.steps == 0
    await episode.call("browser_click", {})
    assert "agent_info" not in episode.trajectory[-1]
    episode.browser.current_url.side_effect = RuntimeError("tab state unavailable")
    await episode.call("browser_take_screenshot", {})
    assert episode.trajectory[-1]["obs"]["url"] == "http://fixture/"
    assert episode.trajectory[-1]["obs"]["url_source"] == "retained"


async def test_uncertain_action_is_failure_not_zero(episode):
    episode.browser.call.side_effect = TimeoutError("in-flight mutation")
    assert (await episode.call("browser_snapshot", {}))["isError"]
    assert (await episode.call("webarena_submit", {"answer": "42"}))["isError"]
    final = await episode.finalize()
    assert final["status"] == "error"
    assert "rewards" not in final


async def test_cancelled_action_is_failure(episode):
    episode.browser.call.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await episode.call("browser_snapshot", {})
    assert (await episode.finalize())["status"] == "error"


async def test_cancelled_url_capture_cannot_publish_incomplete_trajectory(episode):
    episode.browser.current_url.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await episode.call("browser_click", {})
    assert (await episode.finalize())["status"] == "error"


async def test_cancelled_checkpoint_cannot_resume_or_publish_reward(episode, monkeypatch):
    episode.config["max_steps"] = 100
    episode.book = ScoreBook(100)
    episode.steps = 49
    monkeypatch.setattr(
        "webarena_pro_mcp.session.grade", AsyncMock(side_effect=asyncio.CancelledError())
    )
    with pytest.raises(asyncio.CancelledError):
        await episode.call("browser_click", {})
    assert (await episode.call("webarena_submit", {"answer": "42"}))["isError"]
    final = await episode.finalize()
    assert final["status"] == "error" and "rewards" not in final


async def test_failed_grading_does_not_write_reward(episode, monkeypatch):
    monkeypatch.setattr(
        "webarena_pro_mcp.session.grade", AsyncMock(side_effect=RuntimeError("missing evidence"))
    )
    assert (await episode.finalize())["status"] == "error"
    assert "rewards" not in json.loads((episode.artifacts.root / "result.json").read_text())
    state = json.loads((episode.artifacts.root / "evaluation-state.json").read_text())
    assert state["status"] == "error" and "missing evidence" in state["error"]
    assert state["elapsed_seconds"] >= 0


@pytest.mark.parametrize("limit", [50, 100])
async def test_final_action_returns_before_private_grading(episode, monkeypatch, limit):
    episode.config["max_steps"] = limit
    episode.book = ScoreBook(limit)
    episode.steps = limit - 1
    grader = AsyncMock(return_value=({"score": 1, "success": True}, message("Private")))
    monkeypatch.setattr("webarena_pro_mcp.session.grade", grader)
    assert not (await episode.call("browser_click", {}))["isError"]
    assert episode.steps == limit
    assert not (await episode.call("browser_snapshot", {}))["isError"]
    assert not (await episode.call("webarena_submit", {"answer": "42"}))["isError"]
    assert episode.steps == limit
    grader.assert_not_awaited()
    assert (await episode.call("browser_snapshot", {}))["isError"]
    assert (await episode.finalize())["rewards"][f"score_at_{limit}"] == 1
    grader.assert_awaited_once()
    assert (await episode.finalize())["status"] == "graded"
    grader.assert_awaited_once()


async def test_wall_budget_rejects_actions_but_can_grade(episode):
    episode.deadline = 0
    assert (await episode.call("browser_snapshot", {}))["isError"]
    assert episode.steps == 0
    assert (await episode.finalize())["status"] == "graded"


@pytest.mark.parametrize("name,settings,remaining,expected_session,expected_transport", [
    ("media_transcribe", MediaSettings(), 1800, 900, 900),
    ("media_transcribe", MediaSettings(transcription="local"), 1800, 900, 900),
    ("media_extract_frames", MediaSettings(), 1800, 180, 180),
    ("media_transcribe", MediaSettings(timeout=30, transcription_timeout=1200), 1800, 1200, 1200),
    ("media_extract_frames", MediaSettings(timeout=30, transcription_timeout=1200), 1800, 30, 30),
    ("media_transcribe", MediaSettings(), 45, 45, 900),
])
async def test_media_deadlines_reach_session_and_mcp_transport(
    episode, monkeypatch, name, settings, remaining, expected_session, expected_transport,
):
    ref = "m" + "1" * 24
    media_client = SimpleNamespace(call_tool=AsyncMock(return_value=CallToolResult.model_validate(message("Ready"))))
    browser = MCPBrowser(None, ToolPolicy(["http://fixture"], media=settings), 1, media_client)
    browser.inventory = AsyncMock(return_value=[{"ref": ref}])
    browser.current_url = AsyncMock(return_value="http://fixture/")
    episode.browser = browser
    episode.tools.update(schemas(settings))
    episode.config["media"] = settings.as_dict()
    episode.deadline = 1000 + remaining
    monkeypatch.setattr("webarena_pro_mcp.session.time", SimpleNamespace(monotonic=lambda: 1000))
    wait_for = AsyncMock(wraps=asyncio.wait_for)
    monkeypatch.setattr("webarena_pro_mcp.session.asyncio.wait_for", wait_for)

    assert not (await episode.call(name, {"ref": ref}))["isError"]
    assert episode.failure is None
    # Media dispatch precedes the separate, bounded trajectory URL query.
    assert [call.args[1] for call in wait_for.await_args_list] == [expected_session, 5]
    browser.current_url.assert_awaited_once()
    assert media_client.call_tool.call_args.kwargs["read_timeout_seconds"] == expected_transport


@pytest.mark.parametrize("wall_limited", [False, True])
async def test_transcription_timeout_still_ends_trial(episode, wall_limited):
    settings = MediaSettings(transcription_timeout=900 if wall_limited else 0.01)
    episode.config["media"] = settings.as_dict()
    episode.config["wall_seconds"] = 0.01 if wall_limited else 1800
    episode.tools.update(schemas(settings))

    async def never_finishes(*_):
        await asyncio.Event().wait()

    episode.browser.call.side_effect = never_finishes
    result = await episode.call("media_transcribe", {"ref": "m" + "1" * 24})
    assert result["isError"] and "retried" in result["content"][0]["text"]
    assert episode.failure.startswith("TimeoutError")
    assert (await episode.call("browser_snapshot", {}))["isError"]


async def test_timeout_preserves_inputs_and_configured_deadline(episode, monkeypatch):
    from webarena_pro_mcp.evaluation import grade

    monkeypatch.setattr("webarena_pro_mcp.session.grade", grade)
    episode.config["evaluation_timeout"] = 900
    episode.browser.identity = AsyncMock(return_value={
        "target_id": "fixture", "loader_id": "document", "url": "http://fixture",
    })
    episode.browser.call.side_effect = [
        message("Final page evidence"),
        message("- 0: (current) [Fixture](http://fixture)"),
    ]
    episode.supervisor.call.side_effect = TimeoutError("Core/browser supervisor timed out")
    result = await episode.finalize()
    assert result["status"] == "error" and "rewards" not in result
    assert 899 < episode.supervisor.call.call_args.kwargs["timeout"] <= 900
    evidence = json.loads((episode.artifacts.root / "evaluation-0-input.json").read_text())
    assert evidence["snapshot"] == message("Final page evidence")
    state = json.loads((episode.artifacts.root / "evaluation-state.json").read_text())
    assert state["timeout_seconds"] == 900 and state["status"] == "error"
    assert "TimeoutError" in state["error"]


async def test_screenshots_are_private_and_do_not_consume_actions(episode):
    episode.config["record_screenshots"] = True
    png = b"\x89PNG\r\n\x1a\nfixture-image"

    async def call(name, arguments):
        if name == "browser_take_screenshot":
            return {"content": [{"type": "image", "mimeType": "image/png",
                                 "data": base64.b64encode(png).decode()}], "isError": False}
        return message("Ready")

    episode.browser.call.side_effect = call
    await episode.capture_screenshot()
    assert episode.steps == 0 and episode.deadline is None
    assert await episode.call("browser_click", {}) == message("Ready")
    assert episode.steps == 1
    records = [json.loads(x) for x in (episode.artifacts.root / "screenshots.jsonl").read_text().splitlines()]
    assert [(x["step"], x["phase"]) for x in records] == [(0, "initial"), (1, "after_action")]
    for record in records:
        path = episode.artifacts.root / record["image_file"]
        assert path.read_bytes() == png
        assert path.stat().st_mode & 0o777 == 0o600
    calls = (episode.artifacts.root / "calls.jsonl").read_text()
    assert "browser_take_screenshot" not in calls and '"type": "image"' not in calls
    assert (await episode.finalize())["steps"] == 1


async def test_screenshot_error_does_not_change_action_or_grade(episode):
    episode.config["record_screenshots"] = True
    episode.browser.call.side_effect = RuntimeError("Screenshot unavailable")
    result = await episode.call("webarena_submit", {"answer": "42"})
    assert not result["isError"] and episode.failure is None
    assert (await episode.finalize())["rewards"]["success"] == 1
    record = json.loads((episode.artifacts.root / "screenshots.jsonl").read_text())
    assert record["status"] == "unavailable" and "image_file" not in record


async def test_supplementary_screenshot_has_its_own_timeout_after_completed_action(episode):
    episode.config["tool_timeout"] = 0.005
    episode.deadline = time.monotonic() + 0.05
    screenshot_cancelled = asyncio.Event()

    async def call(name, arguments):
        if name == "browser_take_screenshot":
            try:
                await asyncio.sleep(10)
            finally:
                screenshot_cancelled.set()
        return {**message("Saved"), "automatic_observation": message("Saved")}

    episode.browser.call.side_effect = call
    result = await episode.call("browser_click", {})
    assert not result["isError"] and episode.failure is None
    assert episode.steps == 1 and screenshot_cancelled.is_set()
    assert "screenshot unavailable" in json.dumps(result)
    assert (await episode.finalize())["status"] == "graded"


async def test_external_cancellation_during_supplementary_screenshot_aborts_trial(episode):
    async def call(name, arguments):
        if name == "browser_take_screenshot":
            raise asyncio.CancelledError()
        return {**message("Saved"), "automatic_observation": message("Saved")}

    episode.browser.call.side_effect = call
    with pytest.raises(asyncio.CancelledError):
        await episode.call("browser_click", {})
    assert (await episode.finalize())["status"] == "error"


async def test_capture_does_not_extend_exhausted_episode_deadline(episode):
    episode.config["record_screenshots"] = True
    episode.deadline = 0
    await episode.capture_screenshot()
    episode.browser.call.assert_not_awaited()
    record = json.loads((episode.artifacts.root / "screenshots.jsonl").read_text())
    assert record["status"] == "unavailable" and "No episode time remains" in record["error"]


async def test_capture_reuses_agent_requested_screenshot(episode):
    episode.config["record_screenshots"] = True
    png = b"\x89PNG\r\n\x1a\nfixture-image"
    await episode.capture_screenshot({"content": [{"type": "image", "mimeType": "image/png",
                                                  "data": base64.b64encode(png).decode()}]})
    episode.browser.call.assert_not_awaited()
    assert (episode.artifacts.root / "screenshots/step-000000.png").read_bytes() == png
@pytest.mark.parametrize("updates", [
    {"max_steps": 0}, {"max_steps": True}, {"wall_seconds": float("nan")},
    {"tool_timeout": -1}, {"media": {"profile": "omni"}},
    {"urls": {}}, {"urls": {"jobportal": "file:///tmp/site"}},
    {"urls": {"jobportal": "http://user:secret@fixture"}},
    *({"media": {"transcription_timeout": timeout}} for timeout in [
        0, -1, float("nan"), float("inf"), True, "900",
    ]),
])
async def test_invalid_config_never_starts_browser_or_writes_artifacts(task, tmp_path, monkeypatch, updates):
    from webarena_pro_mcp.session import open_session

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid configuration started a supervisor")

    monkeypatch.setattr("webarena_pro_mcp.session.Supervisor", forbidden)
    config = {"task": task.raw_task, "urls": {"jobportal": "http://fixture"}, **updates}
    with pytest.raises(ValueError):
        async with open_session(config, tmp_path / "evidence"):
            pytest.fail("Invalid configuration yielded a session")
    assert not (tmp_path / "evidence").exists()


async def test_failed_startup_still_closes_supervisor(task, tmp_path, monkeypatch):
    from unittest.mock import Mock
    from webarena_pro_mcp.session import open_session

    supervisor = SimpleNamespace(start=AsyncMock(side_effect=RuntimeError("setup failed")), close=AsyncMock())
    monkeypatch.setattr("webarena_pro_mcp.session.Supervisor", Mock(return_value=supervisor))
    with pytest.raises(RuntimeError, match="setup failed"):
        async with open_session({"task": task.raw_task, "urls": {"jobportal": "http://fixture"}}, tmp_path / "evidence"):
            pytest.fail("Failed setup yielded a session")
    supervisor.close.assert_awaited_once()
