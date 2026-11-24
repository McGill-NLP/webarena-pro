"""Recovery boundary tests with real GenericAgent and no external model/site."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
import json
import gzip
import pickle
from types import SimpleNamespace

import numpy as np
import pytest
from agentlab.agents.generic_agent import GenericAgentArgs
from agentlab.llm.chat_api import BaseModelArgs
from agentlab.llm.llm_utils import AIMessage
from agentlab.llm import tracking

from webarena_pro_bgym.agent_flags import FLAGS_VISION
from webarena_pro_bgym.benchmark.benchmark import WebArenaProActionSetArgs
from webarena_pro_bgym.checkpoint import (
    CheckpointRecoveryError, EpisodeCheckpoint, replay_action,
)
from webarena_pro_bgym.study import (
    WebArenaProExpArgs, WebArenaProStepInfo, WebArenaProStepTimeoutError, is_fatal_worker_error,
)


class FakeModel:
    calls = []
    models = []
    responses = ["click('1')", "click('1')", "send_msg_to_user('done')"]
    fail_call = None

    def __init__(self):
        self.models.append(self)

    def __call__(self, messages):
        index = len(self.calls)
        self.calls.append(deepcopy(messages))
        if self.fail_call == index:
            raise WebArenaProStepTimeoutError("provider response lost")
        tracking.TRACKER.instance(5, 2, 0.25)
        return AIMessage(
            f"<think>Remember step {index}.</think><memory>memory {index}</memory>"
            f"<plan>saved plan</plan><step>{index}</step>"
            f"<action>{self.responses[index]}</action>"
        )

    def get_stats(self):
        return {}


@dataclass
class FakeModelArgs(BaseModelArgs):
    model_name: str = "gpt-4o-mini"
    vision_support: bool = False
    max_total_tokens: int = 100000
    max_input_tokens: int = 100000

    def make_model(self):
        return FakeModel()


def make_agent_args():
    flags = deepcopy(FLAGS_VISION)
    flags.use_plan = flags.use_memory = True
    flags.obs.use_screenshot = flags.obs.use_som = False
    flags.action.action_set = WebArenaProActionSetArgs(subsets=("webarena",), multiaction=False)
    return GenericAgentArgs(chat_model_args=FakeModelArgs(), flags=flags)


def observation(step, origin="http://localhost:8000"):
    return {
        "axtree_object": {"nodes": [
            {"nodeId": "1", "role": {"value": "RootWebArea"},
             "name": {"value": f"step {step}"}, "childIds": []},
        ]},
        "dom_object": {"strings": ["HTML", ""], "documents": [{"nodes": {
            "nodeName": [0], "nodeType": [1], "nodeValue": [1], "parentIndex": [-1],
            "attributes": [[]], "contentDocumentIndex": {"index": [], "value": []},
        }}]},
        "extra_element_properties": {},
        "screenshot": np.zeros((8, 8, 3), dtype=np.uint8),
        "axtree_txt": f"RootWebArea step {step}", "pruned_html": "<html/>",
        "url": origin + "/page", "last_action_error": "", "focused_element_bid": "",
        "goal_object": [{"type": "text", "text": "Click twice and finish"}],
        "chat_messages": [], "open_pages_urls": [origin + "/page"],
        "open_pages_titles": ["Fixture"], "active_page_index": 0,
    }


class FakeEnv:
    environments = []
    crash_step = 2
    crash_close = False
    grades = 0
    diverge = False
    origin = "http://localhost:8000"

    def __init__(self):
        self.unwrapped = self
        self.task = SimpleNamespace(
            checkpoint_reset_verified=True,
            instance=SimpleNamespace(urls={"fixture": self.origin}),
        )
        self.steps_taken = 0
        self.actions = []
        self.environments.append(self)

    def reset(self, seed):
        self.steps_taken = 0
        return observation(99 if self.diverge else 0, self.origin), {}

    def register_episode_info(self, episode):
        self.episode_info = episode

    def step(self, action):
        self.steps_taken += 1
        self.actions.append(action)
        # Simulate a mutation that succeeded on the server before the timeout.
        if self.crash_step == self.steps_taken:
            raise WebArenaProStepTimeoutError("browser response lost after mutation")
        done = "send_msg_to_user" in action
        if done and not getattr(self, "_checkpoint_replaying", False):
            type(self).grades += 1
        return observation(self.steps_taken, self.origin), float(done), done, False, {
            "action_exec_start": 0, "action_exec_stop": 0, "action_exec_timeout": 0,
        }

    def close(self):
        if self.crash_close:
            raise WebArenaProStepTimeoutError("close hung")


@dataclass
class FakeEnvArgs:
    task_name: str = "webarena-pro-bgym.1"
    task_seed: int = 0
    max_steps: int = 10

    @property
    def task_config(self):
        return SimpleNamespace(sites=["fixture"])

    def make_env(self, **kwargs):
        return FakeEnv()


@pytest.fixture(autouse=True)
def fake_state(monkeypatch):
    FakeModel.calls = []
    FakeModel.models = []
    FakeModel.fail_call = None
    FakeModel.responses = ["click('1')", "click('1')", "send_msg_to_user('done')"]
    FakeEnv.environments = []
    FakeEnv.crash_step = 2
    FakeEnv.crash_close = FakeEnv.diverge = False
    FakeEnv.grades = 0
    FakeEnv.origin = "http://localhost:8000"
    monkeypatch.setattr("webarena_pro_bgym.study.save_package_versions", lambda _: None)
    monkeypatch.setattr(WebArenaProExpArgs, "_stop_selected_site_containers", lambda _: None)
    monkeypatch.setattr(WebArenaProExpArgs, "_set_logger", lambda _: None)
    monkeypatch.setattr(WebArenaProExpArgs, "_unset_logger", lambda _: None)
    monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "1")


def experiment(tmp_path, *, resume=False, fresh=False):
    exp = WebArenaProExpArgs(agent_args=make_agent_args(), env_args=FakeEnvArgs(),
                            checkpoint_path=tmp_path / "checkpoint.pkl",
                            resume_requested=resume, resume_from_start=fresh,
                            save_screenshot=False)
    exp.prepare(tmp_path)
    return exp


def test_real_generic_agent_runs_literal_special_token_observation(tmp_path, monkeypatch):
    original = FakeEnv.reset
    literal = "Page mentions <|endoftext|> and <|fim_prefix|> literally"

    def reset(self, seed):
        obs, info = original(self, seed)
        obs["axtree_object"]["nodes"][0]["name"]["value"] = literal
        return obs, info

    monkeypatch.setattr(FakeEnv, "reset", reset)
    FakeEnv.crash_step = None
    exp = experiment(tmp_path)
    exp.run()
    summary = json.loads((exp.exp_dir / "summary_info.json").read_text())
    assert exp.err_msg is None
    assert summary["n_steps"] == 3
    assert literal in str(FakeModel.calls[0])
    assert summary["stats.cum_n_token_axtree_txt"] > 0


def test_recovery_replays_coordinate_stroke_without_new_decisions(tmp_path):
    FakeModel.responses = ["mouse_down(40, 60)", "mouse_move(90, 80)",
                           "mouse_up(120, 140)", "send_msg_to_user('done')"]
    first = experiment(tmp_path)
    first.agent_args.flags.action.action_set = WebArenaProActionSetArgs(
        subsets=("webarena", "coord"), multiaction=False,
    )
    first.run()
    assert len(FakeModel.calls) == 2
    assert "Canvas coordinates" in str(FakeModel.calls[0])
    FakeEnv.crash_step = None
    second = experiment(tmp_path, resume=True)
    second.agent_args.flags.action.action_set = deepcopy(first.agent_args.flags.action.action_set)
    second.run()
    assert second.err_msg is None
    assert len(FakeModel.calls) == 4
    assert FakeEnv.environments[-1].actions == FakeModel.responses


def test_episode_failure_saves_original_error_and_nested_agent_info(tmp_path, monkeypatch):
    from bgym import AgentInfo
    from agentlab.agents.generic_agent.generic_agent import GenericAgent

    original = GenericAgent.get_action

    def get_action(self, obs):
        action, info = original(self, obs)
        info.extra_info = {"nested": [AgentInfo(think="saved before crash")]}
        return action, info

    monkeypatch.setattr(GenericAgent, "get_action", get_action)
    exp = experiment(tmp_path)
    exp.run()
    summary = json.loads((exp.exp_dir / "summary_info.json").read_text())
    assert "browser response lost after mutation" in summary["err_msg"]
    assert "WebArenaProStepTimeoutError" in summary["stack_trace"]
    with gzip.open(exp.exp_dir / "step_0.pkl.gz", "rb") as saved:
        step = pickle.load(saved)
    assert step.agent_info["extra_info"]["nested"][0]["think"] == "saved before crash"
    assert summary["stats.cum_cost"] == 0.5


def test_rebuild_continues_real_generic_agent_without_repeating_paid_decisions(tmp_path):
    first = experiment(tmp_path)
    first.run()
    assert "WebArenaProStepTimeoutError" in first.err_msg
    assert len(FakeModel.calls) == 2
    assert FakeEnv.environments[0].steps_taken == 2
    checkpoint = EpisodeCheckpoint.for_experiment(first)
    assert checkpoint.load()["phase"] == "step_pending"
    assert checkpoint.data["agent"]["actions"] == ["click('1')", "click('1')"]

    FakeEnv.crash_step = None
    FakeEnv.origin = "http://localhost:9000"  # a different reserved runtime
    second = experiment(tmp_path, resume=True)
    second.run()
    assert second.err_msg is None
    assert len(FakeModel.calls) == 3
    assert FakeEnv.environments[1].actions == ["click('1')", "click('1')", "send_msg_to_user('done')"]
    assert FakeEnv.grades == 1
    checkpoint = EpisodeCheckpoint.for_experiment(second)
    data = checkpoint.load()
    assert data["phase"] == "finished"
    assert len(data["agent"]["obs_history"]) == 3
    assert len(data["agent"]["actions"]) == 3
    assert len(data["agent"]["thoughts"]) == 3
    assert data["agent"]["plan"] == "saved plan"
    assert data["agent"]["plan_step"] == "2"
    assert all("localhost:8000" not in str(obs) for obs in data["agent"]["obs_history"])
    summary = json.loads((second.exp_dir / "summary_info.json").read_text())
    assert summary["n_steps"] == 3
    assert summary["stats.cum_cost"] == 0.75


@pytest.mark.parametrize("phase", ["model_pending", "evaluation_pending", "external_pending", "verifier_pending"])
def test_ambiguous_paid_outcome_refuses_before_creating_model_or_browser(tmp_path, phase):
    first = experiment(tmp_path)
    first.run()
    checkpoint = EpisodeCheckpoint.for_experiment(first)
    checkpoint.load()
    checkpoint.mark(phase)
    counts = len(FakeModel.models), len(FakeEnv.environments), len(FakeModel.calls)
    second = experiment(tmp_path, resume=True)
    second.run()
    assert "paid call may have completed" in second.err_msg
    assert counts == (len(FakeModel.models), len(FakeEnv.environments), len(FakeModel.calls))


def test_live_provider_timeout_remains_ambiguous(tmp_path, monkeypatch):
    cleanup = []
    monkeypatch.setattr(FakeEnv, "close", lambda self: cleanup.append("close"))
    monkeypatch.setattr(WebArenaProExpArgs, "_unset_logger", lambda self: cleanup.append("logger"))
    FakeModel.fail_call = 1
    first = experiment(tmp_path)
    first.run()
    assert "provider response lost" in first.err_msg
    assert is_fatal_worker_error(first.worker_fatal_error, first.stack_trace)
    summary = json.loads((first.exp_dir / "summary_info.json").read_text())
    assert "WebArenaProStepTimeoutError" in summary["err_msg"]
    assert summary["truncated"]
    assert summary["stats.cum_cost"] == 0.25
    assert cleanup == ["close", "logger"]
    second = experiment(tmp_path, resume=True)
    second.run()
    assert "model_pending" in second.err_msg
    assert len(FakeModel.calls) == 2


def test_divergent_reset_refuses_before_mutation_or_new_model_work(tmp_path):
    experiment(tmp_path).run()
    FakeEnv.crash_step = None
    FakeEnv.diverge = True
    second = experiment(tmp_path, resume=True)
    second.run()
    assert "observation diverged at step 0" in second.err_msg
    assert len(FakeModel.calls) == 2
    assert FakeEnv.environments[-1].actions == []


def test_full_retry_archives_checkpoint_and_deliberately_buys_new_decisions(tmp_path):
    experiment(tmp_path).run()
    FakeEnv.crash_step = None
    FakeModel.responses += ["send_msg_to_user('done')"]
    fresh = experiment(tmp_path, resume=True, fresh=True)
    fresh.run()
    assert fresh.err_msg is None
    assert len(FakeModel.calls) == 3
    assert FakeEnv.environments[-1].actions == ["send_msg_to_user('done')"]
    assert len(list(tmp_path.glob("checkpoint.previous-*.pkl"))) == 1
    assert json.loads((fresh.exp_dir / "summary_info.json").read_text())["n_steps"] == 1


def test_finished_checkpoint_recovers_close_timeout_without_regrading(tmp_path, monkeypatch):
    cleanup = []
    monkeypatch.setattr(WebArenaProExpArgs, "_stop_selected_site_containers",
                        lambda self: cleanup.append("containers"))
    monkeypatch.setattr(WebArenaProExpArgs, "_unset_logger", lambda self: cleanup.append("logger"))
    FakeEnv.crash_step = None
    FakeEnv.crash_close = True
    first = experiment(tmp_path)
    first.run()
    assert first.worker_fatal_error
    assert is_fatal_worker_error(first.worker_fatal_error, first.stack_trace)
    assert cleanup == ["containers", "logger"]
    assert "close hung" in json.loads((first.exp_dir / "summary_info.json").read_text())["err_msg"]
    assert FakeEnv.grades == 1
    second = experiment(tmp_path, resume=True)
    second.run()
    assert second.err_msg is None and second.worker_fatal_error is None
    assert len(FakeModel.calls) == 3
    assert len(FakeEnv.environments) == 1
    assert FakeEnv.grades == 1


def test_missing_checkpoint_and_changed_configuration_never_silently_restart(tmp_path):
    exp = experiment(tmp_path, resume=True)
    exp.run()
    assert "no durable checkpoint" in exp.err_msg
    assert not FakeModel.calls
    experiment(tmp_path).run()
    exp = experiment(tmp_path, resume=True)
    exp.env_args.max_steps += 1
    exp.run()
    assert "configuration changed" in exp.err_msg
    assert len(FakeModel.calls) == 2


def test_checkpoint_is_atomic_private_and_cross_day_recovery_requires_full_retry(tmp_path):
    first = experiment(tmp_path)
    first.run()
    checkpoint = EpisodeCheckpoint.for_experiment(first)
    checkpoint.load()
    assert checkpoint.path.stat().st_mode & 0o777 == 0o600
    checkpoint.path.with_suffix(".tmp").write_bytes(b"incomplete write")
    assert checkpoint.load()["phase"] == "step_pending"
    checkpoint.data["day"] = date.today() - timedelta(days=1)
    checkpoint.write()
    with pytest.raises(CheckpointRecoveryError, match="execution date changed"):
        checkpoint.load()


@pytest.mark.parametrize("action", ["transcribe('http://site/audio')", "listen('http://site/audio')", "watch('http://site/video')",
                                     "import os", "click(find_target())", "upload_file('1', '/tmp/a')"])
def test_unsupported_replay_cannot_repeat_paid_media_or_arbitrary_code(action):
    with pytest.raises(CheckpointRecoveryError, match="not supported"):
        replay_action(action, {})


def test_url_rewrite_does_not_rewrite_same_prefix_on_unrelated_host():
    assert replay_action("goto('http://localhost:8000/page')", {
        "http://localhost:8000": "http://localhost:9000",
    }) == "goto('http://localhost:9000/page')"
    assert replay_action("fill('1', 'http://localhost:80000/page')", {
        "http://localhost:8000": "http://localhost:9000",
    }) == "fill('1', 'http://localhost:80000/page')"


def test_replay_cannot_navigate_outside_the_reset_websites():
    with pytest.raises(CheckpointRecoveryError, match="not supported"):
        replay_action("goto('https://outside.example/')", {}, {"localhost:8000"})


def test_ready_checkpoint_continues_at_next_decision_not_previous_one(tmp_path, monkeypatch):
    original = EpisodeCheckpoint.save

    def crash_after_commit(self, phase, episode, agent, env):
        original(self, phase, episode, agent, env)
        if phase == "ready" and len(episode) == 2:
            raise WebArenaProStepTimeoutError("worker died after durable step commit")

    monkeypatch.setattr(EpisodeCheckpoint, "save", crash_after_commit)
    first = experiment(tmp_path)
    first.run()
    assert len(FakeModel.calls) == 1
    monkeypatch.setattr(EpisodeCheckpoint, "save", original)
    FakeEnv.crash_step = None
    second = experiment(tmp_path, resume=True)
    second.run()
    assert second.err_msg is None
    assert len(FakeModel.calls) == 3
    assert FakeEnv.environments[-1].steps_taken == 3


@pytest.mark.parametrize("crash_step", [50, 100])
@pytest.mark.parametrize("max_steps", [-1, 150])
def test_cutoff_evaluation_is_marked_pending_before_the_browser_step(tmp_path, crash_step, max_steps):
    FakeModel.responses = ["click('1')"] * crash_step
    FakeEnv.crash_step = crash_step
    exp = experiment(tmp_path)
    exp.env_args.max_steps = max_steps
    exp.run()
    assert "browser response lost" in exp.err_msg
    checkpoint = EpisodeCheckpoint.for_experiment(exp)
    with pytest.raises(CheckpointRecoveryError, match="evaluation_pending"):
        checkpoint.load()


@pytest.mark.parametrize("cutoff", [50, 100])
@pytest.mark.parametrize("max_steps", [-1, 150])
def test_resume_preserves_cutoff_score_without_repeating_evaluation(tmp_path, monkeypatch, cutoff, max_steps):
    FakeModel.responses = ["click('1')"] * (cutoff + 1) + ["send_msg_to_user('done')"]
    FakeEnv.crash_step = cutoff + 1
    original = FakeEnv.step
    evaluations = []

    def step_with_cutoff(self, action):
        obs, reward, done, truncated, info = original(self, action)
        if self.steps_taken == cutoff and not getattr(self, "_checkpoint_replaying", False):
            evaluations.append(self.steps_taken)
            info["task_info"] = {
                "score": 0.5, "dag_evaluated": True, "evaluation_trigger": "budget_checkpoint",
            }
        return obs, reward, done, truncated, info

    monkeypatch.setattr(FakeEnv, "step", step_with_cutoff)
    first = experiment(tmp_path)
    first.env_args.max_steps = max_steps
    first.run()
    assert "browser response lost" in first.err_msg
    FakeEnv.crash_step = None
    second = experiment(tmp_path, resume=True)
    second.env_args.max_steps = max_steps
    second.run()
    assert second.err_msg is None
    assert evaluations == [cutoff]
    summary = json.loads((second.exp_dir / "summary_info.json").read_text())
    assert summary["step_budget_scores"][str(cutoff)] == {
        "score": 0.5, "success": False, "evaluated_at_step": cutoff,
    }


def test_write_ahead_failure_does_not_issue_a_model_call(tmp_path, monkeypatch):
    original = EpisodeCheckpoint.write

    def fail_pending(self):
        if self.data["phase"] == "model_pending":
            raise OSError("fsync failed")
        original(self)

    monkeypatch.setattr(EpisodeCheckpoint, "write", fail_pending)
    first = experiment(tmp_path)
    first.run()
    assert "fsync failed" in first.err_msg
    assert not FakeModel.calls


def test_reset_timeout_before_paid_calls_can_safely_resume(tmp_path, monkeypatch):
    original = FakeEnv.reset
    monkeypatch.setattr(FakeEnv, "reset", lambda *a, **kw: (_ for _ in ()).throw(
        WebArenaProStepTimeoutError("reset hung")))
    experiment(tmp_path).run()
    assert not FakeModel.calls
    monkeypatch.setattr(FakeEnv, "reset", original)
    FakeEnv.crash_step = None
    resumed = experiment(tmp_path, resume=True)
    resumed.run()
    assert resumed.err_msg is None
    assert len(FakeModel.calls) == 3


def test_disabled_reset_refuses_before_repeating_model_work(tmp_path, monkeypatch):
    experiment(tmp_path).run()
    monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "0")
    second = experiment(tmp_path, resume=True)
    second.run()
    assert "reset is disabled" in second.err_msg
    assert len(FakeEnv.environments) == 1 and len(FakeModel.calls) == 2


def test_noop_reset_backend_never_replays_on_mutated_site_state(tmp_path, monkeypatch):
    experiment(tmp_path).run()
    monkeypatch.setenv("WP_RESET_BACKEND", "none")
    second = experiment(tmp_path, resume=True)
    second.run()
    assert "reset is disabled" in second.err_msg
    assert len(FakeEnv.environments) == 1 and len(FakeModel.calls) == 2


def test_real_task_configuration_identity_ignores_runtime_origin_but_preserves_semantics(tmp_path):
    from webarena_pro_bgym.benchmark.env import WebArenaProEnvArgs
    from webarena_pro_core.task import WebArenaProTaskConfig

    config = WebArenaProTaskConfig(
        task_id="1", intent="Fixture", sites=("mattermost",), container_name="fixture",
        start_url="http://localhost:8000/channel?x=1", login_page="http://localhost:8000/login",
        raw_task={"task_id": 1, "intent": "Fixture", "sites": ["mattermost"]},
    )
    first = WebArenaProExpArgs(agent_args=make_agent_args(),
                              env_args=WebArenaProEnvArgs(config, "webarena-pro-bgym.1"),
                              checkpoint_path=tmp_path / "checkpoint.pkl")
    second = deepcopy(first)
    second.env_args.task_config.start_url = "http://localhost:9000/channel?x=1"
    second.env_args.task_config.login_page = "http://localhost:9000/login"
    assert EpisodeCheckpoint.for_experiment(first).identity == EpisodeCheckpoint.for_experiment(second).identity
    second.env_args.task_config.start_url += "&semantic_change=1"
    assert EpisodeCheckpoint.for_experiment(first).identity != EpisodeCheckpoint.for_experiment(second).identity


def test_saved_model_requests_cover_sdk_and_parser_retries(tmp_path, monkeypatch):
    import httpx
    from jsonschema import Draft202012Validator
    from openai import OpenAI

    from webarena_pro_bgym.llm_configs import GeminiChatModel
    from webarena_pro_bgym.model_requests import write_run_usage
    from webarena_pro_core.model_requests import ModelRequest

    monkeypatch.setenv("GEMINI_API_KEY", "fixture-provider-secret")
    attempts = 0

    def serve(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, headers={"retry-after-ms": "1"}, json={
                "error": {"message": "retry fixture-provider-secret", "api_key": "nested-secret"},
            })
        parsed = attempts == 3
        action = "<action>send_msg_to_user('done')</action>" if parsed else "missing action tag"
        return httpx.Response(200, headers={"x-request-id": f"req-{attempts}"}, json={
            "id": f"completion-{attempts}", "model": "served-model", "provider": "route-a",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": action}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 10,
                      "prompt_tokens_details": {"cached_tokens": 400},
                      "completion_tokens_details": {"reasoning_tokens": 4}},
        })

    def make_model(_):
        model = GeminiChatModel("requested-model")
        model.client.close()
        model.client = OpenAI(api_key="fixture-provider-secret",
                              http_client=httpx.Client(transport=httpx.MockTransport(serve)))
        return model

    monkeypatch.setattr(FakeModelArgs, "make_model", make_model)
    exp = experiment(tmp_path)
    exp.run()
    assert exp.err_msg is None
    directory = exp.exp_dir
    assert json.loads((directory / "summary_info.json").read_text())["n_steps"] == 1
    rows = [ModelRequest.model_validate_json(line)
            for line in (directory / "model_requests.jsonl").read_text().splitlines()]
    assert [(r.step_id, r.attempt, r.call_reason, r.http_status) for r in rows] == [
        (0, 1, "action", 503), (0, 2, "action", 200), (0, 1, "parser_retry", 200),
    ]
    failed, retry, followup = rows
    assert failed.call_id == retry.call_id != followup.call_id
    assert failed.status == "failed" and failed.usage.input_tokens.total is None
    assert followup.provider_request_id == "req-3"
    assert (followup.model_requested, followup.model_served, followup.route) == (
        "requested-model", "served-model", "route-a")
    bodies = [json.loads((directory / r.raw_response_path).read_text()) for r in rows]
    assert bodies[0]["error"] == {"message": "retry [REDACTED]", "api_key": "[REDACTED]"}
    assert bodies[1]["choices"][0]["message"]["content"] == "missing action tag"
    assert "send_msg_to_user" in bodies[2]["choices"][0]["message"]["content"]
    requests = [json.loads((directory / r.raw_request_path).read_text()) for r in rows]
    assert requests[0] == requests[1]
    assert requests[2]["messages"][-2]["content"] == "missing action tag"
    assert requests[2]["messages"][-1]["role"] == "user"

    summary = json.loads((directory / "model_usage.json").read_text())
    assert (summary["request_count"], summary["failed_count"], summary["retry_count"]) == (3, 1, 1)
    assert summary["steps"]["0"]["metrics"] == summary["metrics"]
    for field in ("regular", "cached", "total"):
        reported = [getattr(row.usage.input_tokens, field) for row in rows
                    if getattr(row.usage.input_tokens, field) is not None]
        assert summary["metrics"][f"input_tokens.{field}"] == {
            "sum": sum(reported), "reported_requests": len(reported),
        }
    assert summary["metrics"]["input_tokens.regular"]["sum"] == 1200
    assert summary["metrics"]["input_tokens.cached"]["sum"] == 800
    assert summary["metrics"]["output_tokens.total"]["sum"] == 20
    assert summary["metrics"]["output_tokens.text"] == {"sum": None, "reported_requests": 0}

    resumed = experiment(tmp_path, resume=True)
    resumed.run()
    assert (resumed.exp_dir / "model_requests.jsonl").read_bytes() == (directory / "model_requests.jsonl").read_bytes()
    write_run_usage(tmp_path)
    study = json.loads((tmp_path / "model_usage.json").read_text())
    assert study["recorded_episodes"] == 1 and study["request_count"] == 3
    assert study["metrics"] == summary["metrics"]
    assert attempts == 3
    validator = Draft202012Validator(json.loads((tmp_path / "model_request.schema.json").read_text()))
    for row in rows:
        validator.validate(row.model_dump(mode="json"))
