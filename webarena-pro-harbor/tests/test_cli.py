import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from jsonschema import validate
from webarena_pro_core.atif_usage import HarborRequestUsage, export_job
from webarena_pro_core.model_requests import RunRequests

from webarena_pro_harbor.cli import build_runtime, main, select_tasks


def test_task_selection_keeps_split_and_site_boundaries():
    selected = select_tasks("test", "all", "1,002")
    assert {task.task_id for task in selected} == {"001", "002"}
    with pytest.raises(ValueError, match="Tasks not found"):
        select_tasks("dev", "all", "001")
    with pytest.raises(ValueError, match="Tasks not found"):
        select_tasks("test", "all", "999999")
    task = selected[0]
    assert select_tasks("test", task.website, task.task_id)[0].task_id == task.task_id


@pytest.mark.parametrize("command", ["serve", "finalize"])
def test_existing_runtime_commands_delegate_to_mcp(tmp_path, monkeypatch, command):
    calls = []

    async def invoke(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(f"webarena_pro_mcp.server.{command}", invoke)
    socket = tmp_path / "control.sock"
    flags = ["webarena-pro-harbor", command, "--socket", str(socket)]
    if command == "serve":
        config, evidence = tmp_path / "session.json", tmp_path / "evidence"
        flags += ["--config", str(config), "--directory", str(evidence), "--port", "8080"]
    monkeypatch.setattr("sys.argv", flags)
    main()
    if command == "serve":
        assert calls == [((config, evidence, socket, 8080), {"host": "0.0.0.0"})]
    else:
        assert calls == [((socket, 360), {})]


def test_build_runtime_bundles_core_browser_helpers_and_media(tmp_path, monkeypatch):
    packages = {
        "webarena-pro-core",
        "webarena-pro-media",
        "webarena-pro-mcp",
        "webarena-pro-harbor",
    }
    for name in packages:
        package = tmp_path / name
        package.mkdir()
        (package / "pyproject.toml").touch()
    built = set()

    def run(command, *, check):
        assert check
        if command[:2] == ["uv", "build"]:
            name = Path(command[-1]).name
            built.add(name)
            (Path(command[command.index("--out-dir") + 1]) / f"{name}.whl").touch()
        else:
            assert command[:-1] == [
                "docker",
                "build",
                "--tag",
                "webarena-pro-harbor:test",
                "--platform",
                "linux/amd64",
            ]
            context = Path(command[-1])
            assert {p.stem for p in (context / "wheels").glob("*.whl")} == packages
            assert "COPY wheels/" in (context / "Dockerfile").read_text()

    monkeypatch.setattr("webarena_pro_harbor.cli.subprocess.run", run)
    build_runtime(tmp_path, "webarena-pro-harbor:test", "linux/amd64")
    assert built == packages


@pytest.mark.parametrize(
    ("flags", "profile", "enabled"),
    [
        ([], "standard", True),
        (["--browser-only"], "standard", False),
        (["--native-audio", "--native-video"], "omni", True),
        (["--native-audio"], "omni", True),
        (["--native-video"], "omni", True),
    ],
)
def test_export_cli_selects_media_profile(tmp_path, monkeypatch, task, flags, profile, enabled):
    output = tmp_path / "export"
    monkeypatch.setattr(
        "sys.argv", ["webarena-pro-harbor", "export", "--output", str(output), *flags]
    )
    monkeypatch.setattr("webarena_pro_harbor.cli.select_tasks", lambda *_: [task])
    main()
    config = json.loads(
        (output / "webarena-pro-dev-fixture/environment/browser/episode.json").read_text()
    )
    assert config["media"]["profile"] == profile
    assert config["media"]["enabled"] is enabled
    assert config["media"]["audio"] == ("--native-audio" in flags)
    assert config["media"]["video"] == ("--native-video" in flags)


def test_export_cli_enables_private_screenshot_recording(tmp_path, monkeypatch, task):
    output = tmp_path / "screenshots"
    monkeypatch.setattr("sys.argv", ["webarena-pro-harbor", "export", "--output", str(output),
                                    "--browser-only", "--record-screenshots"])
    monkeypatch.setattr("webarena_pro_harbor.cli.select_tasks", lambda *_: [task])
    main()
    config = json.loads((output / "webarena-pro-dev-fixture/environment/browser/episode.json").read_text())
    assert config["record_screenshots"] is True
    assert config["media"]["enabled"] is False
    assert config["max_steps"] == 50


@pytest.mark.parametrize(
    "flags",
    [
        ["--browser-only", "--native-audio"],
        ["--browser-only", "--native-video"],
        ["--browser-only", "--native-audio", "--native-video"],
    ],
)
def test_export_cli_rejects_incompatible_media(tmp_path, monkeypatch, capsys, flags):
    output = tmp_path / "export"
    monkeypatch.setattr(
        "sys.argv", ["webarena-pro-harbor", "export", "--output", str(output), *flags]
    )
    monkeypatch.setattr("webarena_pro_harbor.cli.select_tasks", lambda *_: [])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "Error:" in capsys.readouterr().err
    assert not output.exists()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def trajectory(steps, **fields):
    return {"schema_version": "ATIF-v1.7", "agent": {"model_name": "fixture"}, "steps": steps, **fields}


def test_export_existing_job(tmp_path, monkeypatch):
    agent = tmp_path / "trial/agent"
    metrics = {"prompt_tokens": 1000, "completion_tokens": 10, "cached_tokens": 400, "extra": {
        "cache_write_input_tokens": 25,
        "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 1000}],
        "cacheTokensDetails": [{"modality": "TEXT", "tokenCount": 400}],
    }}
    one = {"step_id": 1, "source": "agent", "llm_call_count": 1, "metrics": metrics}
    child = trajectory([one], trajectory_id="child")
    root = trajectory([
        {"step_id": 1, "source": "user"},
        dict(one, step_id=2, observation={"results": [{"subagent_trajectory_ref": [
            {"trajectory_id": "child"}, {"trajectory_path": "leaf.json"},
        ]}]}),
        dict(one, step_id=3, llm_call_count=2),
        {"step_id": 4, "source": "agent", "llm_call_count": 0},
        {"step_id": 5, "source": "agent"},
        dict(one, step_id=6, is_copied_context=True),
    ], subagent_trajectories=[child], continued_trajectory_ref="next.json")
    write_json(agent / "trajectory.json", root)
    write_json(agent / "leaf.json", trajectory([dict(one, metrics={"prompt_tokens": 500})]))
    write_json(agent / "next.json", trajectory([dict(one, metrics={"completion_tokens": 0})],
                                               continued_trajectory_ref="leaf.json"))
    write_json(tmp_path / "trial/result.json", {"id": str(uuid4())})
    write_json(tmp_path / "unavailable/result.json", {"id": str(uuid4())})
    monkeypatch.setattr("sys.argv", ["webarena-pro-harbor", "export-usage", str(tmp_path)])
    main()
    saved = json.loads((tmp_path / "model_requests.json").read_text())
    validate(saved, RunRequests.model_json_schema(mode="serialization"))
    assert saved["runner"] == "harbor" and saved["run_id"] == tmp_path.name
    rows = saved["requests"]
    assert len({r["call_id"] for r in rows}) == len(rows) == 4
    first = rows[0]
    assert first["step_id"] == 2 and first["model_requested"] == "fixture"
    assert first["usage"]["input_tokens"] == {
        "total": 1000, "regular": 600, "cached": 400, "cache_write": 25,
        "by_modality": {"text": {"total": 1000, "regular": 600, "cached": 400}},
    }
    assert [r["usage"]["output_tokens"]["total"] for r in rows] == [10, 10, None, 0]
    assert rows[2]["usage"]["input_tokens"]["cached"] is None
    assert {g["reason"] for g in saved["coverage_gaps"]} == {
        "aggregated_calls", "unknown_call_count", "unreadable_trajectory",
    }


def test_plugin_keeps_replaced_trials_and_resume_is_idempotent(tmp_path):
    trial = tmp_path / "task"
    path = trial / "agent/trajectory.json"
    job = SimpleNamespace(job_dir=tmp_path)
    job.on_trial_ended = lambda callback: setattr(job, "ended", callback)
    plugin = HarborRequestUsage()

    async def run():
        await plugin.on_job_start(job)
        for total in (1, 2):
            trial_id = uuid4()
            write_json(path, trajectory([{"step_id": 1, "source": "agent", "llm_call_count": 1,
                                          "metrics": {"prompt_tokens": total, "cached_tokens": 0}}]))
            write_json(trial / "result.json", {"id": str(trial_id)})
            result = SimpleNamespace(exception_info="failed" if total == 1 else None)
            await job.ended(SimpleNamespace(trial_name=trial.name, trial_id=trial_id, result=result))
        await plugin.on_job_end(None)

    asyncio.run(run())
    first = (tmp_path / "model_requests.json").read_bytes()
    saved = export_job(tmp_path)
    assert (tmp_path / "model_requests.json").read_bytes() == first
    assert not saved.coverage_gaps
    assert sorted(row.usage.input_tokens.regular for row in saved.requests) == [1, 2]
    assert len({row.episode_id for row in saved.requests}) == 2


def test_malformed_metrics_preserve_the_inference(tmp_path):
    path = tmp_path / "task/agent/trajectory.json"
    write_json(path, trajectory([{"step_id": 1, "source": "agent", "llm_call_count": 1,
                                  "metrics": {"prompt_tokens": 1, "cached_tokens": 2}}]))
    saved = export_job(tmp_path)
    assert len(saved.requests) == 1 and saved.requests[0].usage.input_tokens.total is None
    assert [g.reason for g in saved.coverage_gaps] == ["invalid_metrics"]
