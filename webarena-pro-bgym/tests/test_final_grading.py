"""Exercise the environment -> task -> DAG -> judge path with a pending step."""

import base64
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import numpy as np
from PIL import Image
import pytest

from browsergym.core import env as browser_env_module
from browsergym.core.env import BrowserEnv
from browsergym.utils.obs import flatten_axtree_to_str
from bgym import AgentInfo
from webarena_pro_bgym.benchmark.env import WebArenaProEnv
from webarena_pro_bgym.benchmark.task import WebArenaProTask
from webarena_pro_bgym.study import WebArenaProExpArgs, WebArenaProStepInfo
from webarena_pro_core.eval import llm_judge
from webarena_pro_core.task import DEPLOYED_WEBSITE_URLS, WebArenaProTaskConfig


def _observation(label, pixel):
    return {
        "url": DEPLOYED_WEBSITE_URLS["nextcloud"],
        "screenshot": np.full((2, 2, 3), pixel, dtype=np.uint8),
        "axtree_object": {
            "nodes": [
                {
                    "nodeId": "1",
                    "role": {"value": "RootWebArea"},
                    "name": {"value": label},
                    "properties": [],
                    "childIds": [],
                }
            ],
        },
        "chat_messages": (),
    }


@pytest.fixture
def browser_env(monkeypatch):
    env = WebArenaProEnv.__new__(WebArenaProEnv)
    env.env_args = SimpleNamespace(max_steps=2)
    env.steps_taken = 1
    env.enable_audio = False
    env.pre_observation_delay = 0
    env.action_mapping = None
    env.terminate_on_infeasible = True
    env.infeasible_message_received = False
    env.page = SimpleNamespace(evaluate=lambda script: [])
    env.page_history = {}
    env.chat = SimpleNamespace(messages=[])
    env.chat.add_message = lambda role, msg: env.chat.messages.append(
        {"role": role, "message": msg}
    )
    events = []
    env.context = SimpleNamespace(cookies=lambda: events.append("callbacks"))
    env._wait_dom_loaded = lambda: events.append("settled")
    env._active_page_check = lambda: events.append("active-page")
    env._wait_for_user_message = lambda: events.append("wait-user")
    env.pre_step = lambda: (
        {"action_exec_start": 0, "action_exec_timeout": 0},
        None,
        None,
    )

    state = {"obs": _observation("BEFORE: unsaved form", 0)}

    def execute(code, page, **kwargs):
        events.append("action")
        state["obs"] = _observation("AFTER: record saved", 255)

    def get_obs(self):
        events.append("observation")
        return deepcopy(state["obs"])

    monkeypatch.setattr(browser_env_module, "execute_python_code", execute)
    monkeypatch.setattr(BrowserEnv, "_get_obs", get_obs)

    config = WebArenaProTaskConfig(
        task_id="final-save",
        intent="Save the record",
        sites=("nextcloud",),
        container_name="test-container",
        start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
        raw_task={"intent": "Save the record"},
        evaluation={
            "operator": "AND",
            "nodes": [
                {
                    "id": "saved",
                    "type": "llm_judge",
                    "eval_config": {
                        "rubric": "The record is saved",
                        "model": "test-judge",
                    },
                }
            ],
        },
    )
    env.task = WebArenaProTask(seed=0, config=config)
    before = deepcopy(state["obs"])
    before["axtree_txt"] = flatten_axtree_to_str(before["axtree_object"])
    env.episode_info = [WebArenaProStepInfo(step=1, obs=before)]
    env.last_step_output = {"obs": before, "episode_info": env.episode_info}
    return env, events


def test_checkpoint_replay_keeps_real_environment_budget_and_suppresses_grading(browser_env):
    env, _ = browser_env
    env.steps_taken = 0
    env.env_args.max_steps = 2
    evaluations = []

    def validate(*args, **kwargs):
        evaluations.append(kwargs["budget_exhausted"])
        return 1.0, False, "", {"dag_evaluated": True}

    env.task.validate = validate
    env._checkpoint_replaying = True
    _, reward, terminated, truncated, info = env.step("click('save')")
    assert evaluations == []
    assert env.steps_taken == 1
    assert reward == 0 and not terminated and not truncated
    assert info["task_info"] == {}

    env._checkpoint_replaying = False
    _, reward, terminated, truncated, _ = env.step("click('save')")
    assert evaluations == [True]
    assert env.steps_taken == 2
    assert reward == 1 and not terminated and truncated


@pytest.mark.parametrize(
    "action",
    [
        "click('save')\nsend_msg_to_user('saved')",
        "click('save')\ndone()",
        "report_infeasible('cannot finish the remaining work')",
        "click('save')",
    ],
)
@pytest.mark.parametrize("successful", [True, False])
def test_final_action_judge_receives_resulting_state(
    browser_env, monkeypatch, action, successful
):
    env, events = browser_env
    prompts = []
    # Match the study loop: the outgoing action belongs to the previous step,
    # while the newly appended step has no observation until from_step returns.
    env.episode_info[-1].action = action
    pending = WebArenaProStepInfo(step=2)
    env.episode_info.append(pending)

    def completion(**kwargs):
        events.append("judge")
        assert pending.obs is None
        prompts.append(kwargs["messages"])
        verdict = "Successful" if successful else "Unsuccessful"
        from openai.types.chat import ChatCompletion
        return ChatCompletion(
            id="test-response", object="chat.completion", created=1, model="test-judge",
            choices=[{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": f"<answer>{verdict}</answer>",
            }}],
        )

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", None)
    monkeypatch.setattr(
        "openai.OpenAI",
        lambda **kwargs: MagicMock(
            base_url="https://judge.example/v1/", max_retries=2,
            chat=SimpleNamespace(completions=SimpleNamespace(create=completion)),
        ),
    )
    pending.from_step(env, action, obs_preprocessor=None)

    assert len(prompts) == 1
    content = prompts[0][1]["content"]
    text = "\n".join(part["text"] for part in content if part["type"] == "text")
    assert "AFTER: record saved" in text
    assert "BEFORE: unsaved form" not in text
    assert action in text
    images = [
        part["image_url"]["url"] for part in content if part["type"] == "image_url"
    ]
    assert len(images) == 1
    actual_image = np.array(
        Image.open(BytesIO(base64.b64decode(images[0].split(",", 1)[1])))
    )
    np.testing.assert_array_equal(actual_image, pending.obs["screenshot"])
    assert np.all(actual_image == 255)
    assert events == [
        "action",
        "callbacks",
        "settled",
        "active-page",
        "wait-user",
        "observation",
        "judge",
    ]
    assert env.steps_taken == env.env_args.max_steps
    assert pending.reward == float(successful)
    assert pending.task_info["score"] == float(successful)
    assert pending.task_info["dag_evaluated"] is True
    assert pending.task_info["dag_results"]["saved"]["passed"] is successful
    audit = pending.task_info["dag_results"]["saved"]["judge_audits"][0]
    assert audit["attempts"][0]["request"]["messages"] == prompts[0]
    assert audit["status"] == ("positive" if successful else "negative")
    assert pending.is_done
    exhausted = action == "click('save')"
    assert pending.truncated is exhausted
    assert pending.terminated is not exhausted
    assert pending.task_info["evaluation_trigger"] == (
        "budget_exhaustion" if exhausted else "agent_completion"
    )
    assert env.last_step_output["truncated"] is exhausted
    assert env.last_step_output["terminated"] is not exhausted
    assert "axtree_txt" not in pending.obs  # agent preprocessing remains separate
    assert env.episode_info[-1] is pending
    assert len(env.episode_info) == 2


def test_ordinary_steps_do_not_grade(browser_env, monkeypatch):
    env, _events = browser_env
    env.env_args.max_steps = 3
    fetch = Mock(side_effect=AssertionError("intermediate backend fetch"))
    monkeypatch.setattr(env.task, "_compute_current_diffs", fetch)
    judge = Mock(side_effect=AssertionError("intermediate judge call"))
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    action = "click('save')"
    env.episode_info[-1].action = action
    pending = WebArenaProStepInfo(step=2)
    env.episode_info.append(pending)

    pending.from_step(env, action, obs_preprocessor=None)

    fetch.assert_not_called()
    judge.assert_not_called()
    assert pending.obs["axtree_object"]
    assert pending.reward == 0.0
    assert pending.task_info == {"score": 0.0, "dag_evaluated": False}
    assert pending.terminated is False
    assert pending.truncated is False


@pytest.mark.parametrize("last_action", ["done()", "click('save')"])
def test_final_step_grades_once_with_full_history_and_evidence(browser_env, monkeypatch, last_action):
    env, _events = browser_env
    env.env_args.max_steps = 3
    baseline = object()
    bundle = {"files": {"baseline": baseline, "current": object(), "diff": object()}}
    env.task.baselines = {"files": baseline}
    env.task.downloads = [{"path": "/tmp/export.csv", "suggested_filename": "export.csv"}]
    fetch = Mock(return_value=bundle)
    monkeypatch.setattr(env.task, "_compute_current_diffs", fetch)
    contexts = []

    def judge(rubric, context, model):
        contexts.append(context)
        return "pass", "saved"

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    for number, action in enumerate(["click('save')", last_action], start=2):
        env.episode_info[-1].action = action
        pending = WebArenaProStepInfo(step=number)
        env.episode_info.append(pending)
        pending.from_step(env, action, obs_preprocessor=None)
        if number == 2:
            assert not pending.is_done
            fetch.assert_not_called()
            assert contexts == []

    fetch.assert_called_once_with()
    assert len(contexts) == 1
    context = contexts[0]
    assert context.trajectory is env.episode_info
    assert [step.action for step in context.trajectory[:-1]] == ["click('save')", last_action]
    assert context.baselines["files"]["baseline"] is baseline
    assert context.downloads == env.task.downloads
    assert "AFTER: record saved" in context.last_step_output["obs"]["axtree_txt"]
    assert pending.reward == 1.0
    assert pending.terminated is (last_action == "done()")
    assert pending.truncated is (last_action != "done()")
    assert pending.task_info["dag_evaluated"] is True

    # A second finalization cannot rerun judges or backend snapshots.
    pending.from_budget_exhaustion(env)
    fetch.assert_called_once_with()
    assert len(contexts) == 1


def test_agent_budget_grades_last_step_without_another_action(browser_env, monkeypatch):
    env, events = browser_env
    env.env_args.max_steps = 50
    contexts = []
    fetch = Mock(return_value={})
    monkeypatch.setattr(env.task, "_compute_current_diffs", fetch)

    def judge(rubric, context, model):
        contexts.append(context)
        return "fail", "unfinished"

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    env.episode_info[-1].action = "click('save')"
    pending = WebArenaProStepInfo(step=2)
    env.episode_info.append(pending)
    pending.from_step(env, "click('save')", obs_preprocessor=None)
    fetch.assert_not_called()
    observation = pending.obs

    pending.from_budget_exhaustion(env)
    pending.from_budget_exhaustion(env)

    assert pending.obs is observation
    assert env.steps_taken == 2
    assert len(env.episode_info) == 2
    assert events.count("action") == 1
    assert events.count("observation") == 1
    fetch.assert_called_once_with()
    assert len(contexts) == 1
    assert contexts[0].trajectory is env.episode_info
    assert contexts[0].last_action == "click('save')"
    assert "AFTER: record saved" in contexts[0].last_step_output["obs"]["axtree_txt"]
    assert pending.reward == 0.0
    assert pending.task_info["dag_evaluated"] is True
    assert pending.task_info["evaluation_trigger"] == "budget_exhaustion"
    assert pending.truncated is True
    assert pending.terminated is False


@pytest.mark.parametrize("scoring, expected_score", [("binary", 0.0), ("partial", 0.5)])
def test_budget_uses_unchanged_rubrics_and_scoring(browser_env, monkeypatch, scoring, expected_score):
    env, _events = browser_env
    evaluation = env.task.config.evaluation
    evaluation["scoring"] = scoring
    evaluation["nodes"].append({
        "id": "missing", "type": "llm_judge",
        "eval_config": {"rubric": "The remaining work is saved", "model": "test-judge"},
    })
    monkeypatch.setattr(
        llm_judge, "_JUDGE_HOOK",
        lambda rubric, context, model: (
            ("pass", "saved") if rubric == "The record is saved" else ("fail", "missing")
        ),
    )
    _, score, terminated, truncated, info = env.step("click('save')")
    assert score == expected_score
    assert info["task_info"]["dag_evaluated"] is True
    assert info["task_info"]["dag_results"]["saved"]["passed"] is True
    assert info["task_info"]["dag_results"]["missing"]["passed"] is False
    assert not terminated and truncated


@pytest.mark.parametrize("max_steps", [1, 2, 30, 50, 100])
def test_exact_step_budget_boundary(browser_env, monkeypatch, max_steps):
    env, events = browser_env
    env.env_args.max_steps = max_steps
    env.steps_taken = 0
    contexts = []

    def judge(rubric, context, model):
        contexts.append(context)
        return "pass", "saved"

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    evaluations = 0
    for step in range(1, max_steps + 1):
        _, score, terminated, truncated, info = env.step("click('save')")
        final = step == max_steps
        evaluated = final or step in (50, 100)
        evaluations += int(evaluated)
        assert score == float(final)
        assert terminated is False
        assert truncated is final
        assert info["task_info"]["dag_evaluated"] is evaluated
        assert len(contexts) == evaluations
        if evaluated:
            assert info["task_info"]["evaluation_trigger"] == (
                "budget_exhaustion" if final else "budget_checkpoint"
            )
    assert events.count("action") == max_steps


@pytest.mark.parametrize("max_steps,final_step", [(100, 100), (-1, 125)])
def test_run_saves_independent_live_cutoff_scores(browser_env, monkeypatch, tmp_path, max_steps, final_step):
    import json

    env, events = browser_env
    env.env_args.max_steps = max_steps
    env.steps_taken = 0
    env.episode_info = [WebArenaProStepInfo(step=0, obs=_observation("Initial", 0))]
    backend_reads = []
    judged = []

    def current_diffs():
        step = env.steps_taken + 1
        backend_reads.append(step)
        return {"live_step": step}

    def get_obs(self):
        step = env.steps_taken + 1
        return _observation(f"State after action {step}", step)

    def judge(rubric, context, model):
        step = context.baselines["live_step"]
        judged.append(step)
        assert f"State after action {step}" in context.last_step_output["obs"]["axtree_txt"]
        assert np.all(context.last_step_output["obs"]["screenshot"] == step)
        assert context.trajectory[-1].step == step
        assert context.trajectory[-1].obs is None  # current observation comes from post_step
        return ("fail" if step == 100 else "pass"), f"State at {step}"

    monkeypatch.setattr(env.task, "_compute_current_diffs", current_diffs)
    monkeypatch.setattr(BrowserEnv, "_get_obs", get_obs)
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    for step in range(1, final_step + 1):
        pending = WebArenaProStepInfo(step=step)
        env.episode_info.append(pending)
        action = "done()" if max_steps == -1 and step == final_step else "click('save')"
        pending.from_step(env, action, obs_preprocessor=None)
        assert pending.is_done is (step == final_step)
        assert pending.reward == float(step == final_step and final_step != 100)

    exp = WebArenaProExpArgs.__new__(WebArenaProExpArgs)
    exp.env_args = env.env_args
    exp.save_summary_info(env.episode_info, tmp_path, None, None)
    summary = json.loads((tmp_path / "summary_info.json").read_text())
    assert backend_reads == judged == ([50, 100] if max_steps != -1 else [50, 100, final_step])
    assert events.count("action") == final_step
    assert summary["cum_reward"] == float(final_step != 100)
    assert summary["max_steps"] == max_steps
    expected = {
        "50": {"score": 1.0, "success": True, "evaluated_at_step": 50},
        "100": {"score": 0.0, "success": False, "evaluated_at_step": 100},
    }
    if max_steps == -1:
        expected["unlimited"] = {"score": 1.0, "success": True, "evaluated_at_step": final_step}
    assert summary["step_budget_scores"] == expected
    for step in judged:
        assert env.episode_info[step].task_info["dag_results"]["saved"]["passed"] is (step != 100)
        assert env.episode_info[step].task_info["dag_trace"]["score"] == float(step != 100)


@pytest.mark.parametrize("cutoff", [50, 100])
@pytest.mark.parametrize("max_steps", [-1, 150])
@pytest.mark.parametrize("ending", ["agent_completion", "budget_exhaustion"])
def test_completion_at_checkpoint_only_grades_once(browser_env, monkeypatch, cutoff, ending, max_steps):
    env, _ = browser_env
    env.env_args.max_steps = max_steps
    env.steps_taken = cutoff - 1
    judge = Mock(return_value=("pass", "saved"))
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    action = "done()" if ending == "agent_completion" else "click('save')"
    _, score, terminated, truncated, info = env.step(action)
    if ending == "budget_exhaustion":
        assert score == 0 and not terminated and not truncated
        score, terminated, truncated, info = env.evaluate_budget_exhaustion()
    assert score == 1.0
    assert terminated is (ending == "agent_completion")
    assert truncated is (ending == "budget_exhaustion")
    assert info["task_info"]["evaluation_trigger"] == ending
    assert judge.call_count == 1


@pytest.mark.parametrize("cutoff", [50, 100])
@pytest.mark.parametrize("max_steps", [-1, 150])
def test_replay_skips_checkpoint_grading(browser_env, monkeypatch, cutoff, max_steps):
    env, _ = browser_env
    env.env_args.max_steps = max_steps
    env.steps_taken = cutoff - 1
    env._checkpoint_replaying = True
    monkeypatch.setattr(env.task, "validate", Mock(side_effect=AssertionError("replay must not grade")))
    _, reward, terminated, truncated, info = env.step("click('save')")
    assert reward == 0.0 and not terminated and not truncated
    assert info["task_info"] == {}
    assert env.steps_taken == cutoff


@pytest.mark.parametrize("max_steps,final_step,failed,expected", [
    (100, 17, False, {"50": 17, "100": 17}),
    (100, 60, False, {"50": 50, "100": 60}),
    (50, 40, False, {"50": 40}),
    (100, 60, True, {"50": 50}),
    (-1, 17, False, {"50": 17, "100": 17, "unlimited": 17}),
    (-1, 60, False, {"50": 50, "100": 60, "unlimited": 60}),
    (-1, 60, True, {"50": 50}),
    (-1, 17, True, {}),
])
def test_summary_uses_early_terminal_score_without_overwriting_checkpoints(
    tmp_path, max_steps, final_step, failed, expected,
):
    import json

    episode = [WebArenaProStepInfo(step=0)]
    if final_step > 50:
        episode.append(WebArenaProStepInfo(step=50, reward=0.0, task_info={
            "score": 1.0, "dag_evaluated": True, "evaluation_trigger": "budget_checkpoint",
        }))
    episode.append(WebArenaProStepInfo(
        step=final_step, reward=0.0, terminated=not failed, truncated=failed, agent_info={},
        task_info={} if failed else {
            "score": 0.5, "dag_evaluated": True, "evaluation_trigger": "agent_completion",
        },
    ))
    exp = WebArenaProExpArgs.__new__(WebArenaProExpArgs)
    exp.env_args = SimpleNamespace(max_steps=max_steps)
    exp.save_summary_info(episode, tmp_path, "browser lost" if failed else None, None)
    summary = json.loads((tmp_path / "summary_info.json").read_text())
    scores = summary["step_budget_scores"]
    evaluated = {budget: record for budget, record in scores.items() if record["score"] is not None}
    assert {budget: record["evaluated_at_step"] for budget, record in evaluated.items()} == expected
    assert set(scores) == ({"50", "100", "unlimited"} if max_steps == -1 else
                           {str(budget) for budget in (50, 100) if budget <= max_steps})
    for record in evaluated.values():
        assert record["score"] == (1.0 if record["evaluated_at_step"] == 50 else 0.5)
        assert record["success"] is (record["evaluated_at_step"] == 50)
    for budget in scores.keys() - evaluated.keys():
        assert scores[budget] == {
            "status": "unavailable", "score": None, "success": None,
            "evaluated_at_step": None, "reason": "episode_error",
            "last_evaluated_score": 1.0 if final_step > 50 else None,
            "last_evaluated_at_step": 50 if final_step > 50 else None,
        }
    if failed and final_step > 50:
        assert summary["cum_reward"] == 1.0
        assert summary["score_provenance"]["status"] == "last_evaluation"


@pytest.mark.parametrize("ending", ["budget", "none", "error", "timeout"])
def test_study_grades_agent_budget_before_saving_and_closing(
    browser_env, monkeypatch, tmp_path, ending
):
    from webarena_pro_bgym import study

    env, events = browser_env
    env.env_args.max_steps = 50
    env.steps_taken = 0

    def reset(seed):
        env.last_action = None
        obs, _, _, _, info = env.post_step({})
        return obs, info

    monkeypatch.setattr(env, "reset", reset)
    monkeypatch.setattr(env, "close", lambda: events.append("close"))
    monkeypatch.setattr(study, "save_package_versions", lambda path: None)
    monkeypatch.setattr(study, "dispatch_step", lambda *args: None)
    monkeypatch.setattr(WebArenaProStepInfo, "make_stats", lambda self: None)
    saved = []
    monkeypatch.setattr(
        WebArenaProStepInfo, "save_step_info",
        lambda self, *args, **kwargs: saved.append((self.reward, deepcopy(self.task_info))),
    )
    actions = iter(["click('save')", None])

    def get_action(obs):
        action = next(actions)
        if action is None and ending in ("error", "timeout"):
            error = study.WebArenaProStepTimeoutError if ending == "timeout" else RuntimeError
            raise error("agent unavailable")
        return action, AgentInfo(extra_info={"budget_exhausted": ending == "budget"})

    agent = SimpleNamespace(
        action_set=SimpleNamespace(to_python_code=lambda action: action),
        obs_preprocessor=None,
        get_action=get_action,
    )
    exp = WebArenaProExpArgs(
        agent_args=SimpleNamespace(make_agent=lambda: agent),
        env_args=SimpleNamespace(
            task_name="budget-test", task_seed=0,
            make_env=lambda **kwargs: env,
        ),
        exp_dir=tmp_path,
        enable_debug=False,
    )
    monkeypatch.setattr(exp, "_set_logger", lambda: None)
    summary = {}

    def save_summary(episode, path, err_msg, stack_trace):
        events.append("summary")
        summary.update(steps=episode, error=err_msg)

    monkeypatch.setattr(exp, "save_summary_info", save_summary)

    def judge(rubric, context, model):
        events.append("judge")
        return "pass", "saved"

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    exp.run()

    final = summary["steps"][-1]
    assert len(summary["steps"]) == 2
    assert events.count("action") == 1
    assert events[-2:] == ["summary", "close"]
    assert final.task_info["dag_evaluated"] is (ending == "budget")
    if ending == "budget":
        assert events.index("judge") < events.index("summary")
        assert final.reward == 1.0
        assert final.truncated and not final.terminated
        assert saved[-1][0] == 1.0
        assert saved[-1][1]["dag_evaluated"] is True
        assert summary["error"] is None
    else:
        assert "judge" not in events
        assert final.reward == 0.0
        assert bool(summary["error"]) is (ending in ("error", "timeout"))


@pytest.mark.parametrize("action", [None, "click('save')", "done()"])
@pytest.mark.parametrize("budget_exhausted", [True, False])
def test_url_guard_still_runs_without_grading(browser_env, monkeypatch, action, budget_exhausted):
    env, _events = browser_env
    outside = Mock(url="https://outside.invalid/")
    outside.goto.side_effect = lambda url, **kwargs: setattr(outside, "url", url)
    env.page.context = SimpleNamespace(
        pages=[outside]
    )
    fetch = Mock(side_effect=AssertionError("unauthorized-page backend fetch"))
    monkeypatch.setattr(env.task, "_compute_current_diffs", fetch)
    judge = Mock(side_effect=AssertionError("unauthorized-page judge call"))
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)

    reward, done, _message, info = env.task.validate(
        env.page, [], last_action=action, budget_exhausted=budget_exhausted
    )

    assert reward == 0.0
    assert done is False
    assert outside.url == "about:blank"
    assert info == {"dag_evaluated": False, "navigation_blocked": True}
    fetch.assert_not_called()
    judge.assert_not_called()


def test_post_step_preserves_validation_messages_and_page_history(browser_env):
    env, events = browser_env
    original_page = env.page
    original_history = env.page_history.copy()

    def validate(*args, **kwargs):
        events.append("validate")
        env.page = object()
        env.page_history = {"changed": 1}
        return 0.5, True, "Task feedback", {"score": 0.5}

    env.task.validate = validate
    obs, reward, terminated, truncated, info = env.post_step({})

    assert events.index("observation") < events.index("validate")
    assert env.page is original_page
    assert env.page_history == original_history
    assert obs["chat_messages"] == ({"role": "user", "message": "Task feedback"},)
    assert env.last_step_output["obs"]["chat_messages"] == obs["chat_messages"]
    assert (reward, terminated, truncated) == (0.5, True, False)
    assert info["task_info"] == {"score": 0.5}
    assert env.last_step_output["reward"] == reward
    assert env.last_step_output["terminated"] is terminated
    assert info["get_observation_stop"] <= info["validation_start"]


@pytest.mark.parametrize("infeasible", [True, False])
def test_post_step_without_validation(browser_env, infeasible):
    env, events = browser_env
    env.infeasible_message_received = infeasible

    def unexpected_validation(*args, **kwargs):
        pytest.fail("validate=False must skip task validation")

    env.task.validate = unexpected_validation
    obs, reward, terminated, truncated, info = env.post_step({}, validate=False)

    assert events == ["callbacks", "settled", "observation"]
    assert obs["axtree_object"]
    assert (reward, terminated, truncated) == (0.0, infeasible, False)
    assert info["task_info"] == {}


def test_summary_persists_portable_judge_evidence_sidecar(tmp_path):
    import json
    from webarena_pro_core.eval.judge_audit import find_audits

    audit = {"schema_version": 1, "audit_id": "unique", "attempts": [{"request": {"messages": ["exact evidence"]}}]}
    step = WebArenaProStepInfo(step=0, agent_info={}, stats={}, task_info={
        "dag_results": {"watched": {"passed": False, "judge_audits": [audit]}}
    })
    exp = WebArenaProExpArgs.__new__(WebArenaProExpArgs)
    exp.save_summary_info([step], tmp_path, None, None)
    path = tmp_path / "judge_audits.json"
    saved = json.loads(path.read_text())
    assert saved[0]["node_id"] == "watched"
    assert saved[0]["step"] == 0
    assert find_audits(saved) == [audit]
    assert path.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "summary_info.json").exists()


def test_infeasible_termination_grades_current_state_once(browser_env, monkeypatch):
    env, _ = browser_env
    env.env_args.max_steps = 100
    env.infeasible_message_received = True
    judge = Mock(return_value=("pass", "saved before reporting infeasible"))
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    _, reward, terminated, truncated, info = env.step("click('save')")
    assert reward == 1.0 and terminated and not truncated
    assert info["task_info"]["evaluation_trigger"] == "early_termination"
    assert info["task_info"]["termination_reason"] == "agent_infeasible"
    env.evaluate_budget_exhaustion()
    judge.assert_called_once()


def test_ungraded_termination_retains_quarter_score_and_marks_later_budget_unavailable(tmp_path):
    import json

    checkpoint = WebArenaProStepInfo(step=50, reward=0.0, task_info={
        "score": 0.25, "dag_evaluated": True, "evaluation_trigger": "budget_checkpoint",
    })
    episode = [checkpoint, WebArenaProStepInfo(step=51, reward=0.0, terminated=True, task_info={
        "error": "browser unavailable", "dag_evaluated": False,
    })]
    exp = WebArenaProExpArgs.__new__(WebArenaProExpArgs)
    exp.env_args = SimpleNamespace(max_steps=100)
    exp.save_summary_info(episode, tmp_path, None, None)
    summary = json.loads((tmp_path / "summary_info.json").read_text())
    assert summary["cum_reward"] == 0.25
    assert summary["step_budget_scores"]["50"] == {
        "score": 0.25, "success": False, "evaluated_at_step": 50,
    }
    assert summary["step_budget_scores"]["100"]["score"] is None
    assert summary["step_budget_scores"]["100"]["last_evaluated_score"] == 0.25
    assert summary["step_budget_scores"]["100"]["reason"] == "episode_ended_without_evaluation"
    assert checkpoint.task_info["score"] == 0.25 and checkpoint.reward == 0.0
