"""Identical-input reuse tests use scripted responses, not model-quality claims."""
import copy
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_judge_audit import client, context, response
from webarena_pro_core.eval import judge_audit, llm_judge
from webarena_pro_core.eval.dag import DAGEvaluator, NodeResult, parse_eval_dag
from webarena_pro_core.eval.judge_cache import JudgeVerdictCache
from webarena_pro_core.eval.snapshot import Snapshot, build_snapshot_bundle
LEGACY_TASKS = json.loads((Path(__file__).parent / "fixtures/issue83_legacy_tasks.json").read_text())


def legacy_task(task_id):
    task = copy.deepcopy(next(task for task in LEGACY_TASKS if task["task_id"] == task_id))
    # Keep the archived judge strategies while using the current scoring API.
    task["eval"]["scoring"] = "partial"
    for node in task["eval"]["nodes"]:
        node.pop("weight", None)
    return task


def cached_context():
    ctx = context()
    ctx.judge_cache = JudgeVerdictCache()
    return ctx


def grade(ctx, **config):
    return llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "Watch the full video", **config}, ctx)


@pytest.mark.parametrize("answer,passed", [("Successful", True), ("Unsuccessful", False)])
def test_identical_evidence_reuses_valid_pass_and_fail_with_provenance(client, answer, passed):
    client.chat.completions.create.side_effect = [
        response(f"<answer>{answer}</answer>"),
        response("<answer>In Progress</answer>"),
    ]
    ctx = cached_context()
    assert grade(ctx).passed is passed
    source = copy.deepcopy(ctx.judge_audits[-1])
    assert grade(ctx).passed is passed
    hit = ctx.judge_audits[-1]
    assert client.chat.completions.create.call_count == 1
    assert hit["attempts"] == []
    assert hit["reuse"]["status"] == "hit"
    assert hit["reuse"]["source_audit_id"] == source["audit_id"]
    assert hit["source_audit"] == source
    assert hit["audit_id"] != source["audit_id"]
    assert hit["completion_kwargs"] == source["completion_kwargs"]
    assert hit["reuse"]["input_sha256"] == source["reuse"]["input_sha256"]
    assert "SECRET_KEY_MUST_NOT_BE_SAVED" not in json.dumps(hit)
    assert judge_audit.submitted_audit(hit) == source


@pytest.mark.parametrize("change", [
    "axtree", "screenshot", "trajectory_action", "trajectory_reasoning", "current_url",
    "task_id", "task_intent", "task_condition", "date", "last_action", "chat", "downloads", "backend",
])
def test_captured_evidence_and_condition_changes_invalidate(client, change):
    client.chat.completions.create.side_effect = [
        response("<answer>Successful</answer>"), response("<answer>Unsuccessful</answer>"),
    ]
    ctx = cached_context()
    assert grade(ctx).passed
    if change == "axtree":
        ctx.last_step_output["obs"]["axtree_txt"] = "VIDEO STOPPED"
    elif change == "screenshot":
        ctx.last_step_output["obs"]["screenshot"][0, 0, 0] = 255
    elif change == "trajectory_action":
        ctx.trajectory[0]["action"] = "click('stop')"
    elif change == "trajectory_reasoning":
        ctx.trajectory[0]["agent_info"]["think"] = "stop video"
    elif change == "current_url":
        ctx.last_step_output["obs"]["url"] = "http://yt-lite/elsewhere"
    elif change == "task_id":
        ctx.task_config["task_id"] = "different"
    elif change == "task_intent":
        ctx.task_config["intent"] = "Do not watch"
    elif change == "task_condition":
        ctx.judge_dag_config = {"new_condition": True}
    elif change == "date":
        ctx.task_start_date = date(2026, 10, 20)
    elif change == "last_action":
        ctx.last_action = "stop"
    elif change == "chat":
        ctx.chat_messages.append({"role": "assistant", "message": "No longer watched"})
    elif change == "downloads":
        ctx.downloads.append({"path": "/unused/file", "url": "http://yt-lite/file"})
    elif change == "backend":
        ctx.baselines["state"] = build_snapshot_bundle(Snapshot(), Snapshot({"x": {"etag": "changed"}}))
    assert not grade(ctx).passed
    assert client.chat.completions.create.call_count == 2
    assert ctx.judge_audits[-1]["reuse"]["status"] == "miss"


@pytest.mark.parametrize("change", ["model", "sampling", "retries", "endpoint", "prompt", "rubric", "node"])
def test_effective_request_changes_invalidate(client, monkeypatch, change):
    client.chat.completions.create.side_effect = [
        response("<answer>Successful</answer>"), response("<answer>Unsuccessful</answer>"),
    ]
    ctx = cached_context()
    assert grade(ctx).passed
    config = {}
    if change == "model":
        config["model"] = "gemini-other"
    elif change == "sampling":
        config["sampling"] = {"temperature": 0}
    elif change == "retries":
        config["max_retries"] = 0
    elif change == "endpoint":
        client.base_url = "https://different.example/v1"
    elif change == "prompt":
        monkeypatch.setattr(judge_audit, "PROMPT_VERSION", "new-version")
    elif change == "rubric":
        config["rubric"] = "Watch a different video"
    elif change == "node":
        ctx.judge_node_id = "another-node"
    assert not grade(ctx, **config).passed
    assert client.chat.completions.create.call_count == 2


def test_state_reversal_and_return_to_old_state_are_rejudged(client):
    client.chat.completions.create.side_effect = [
        response("<answer>Successful</answer>"),
        response("<answer>Unsuccessful</answer>"),
        response("<answer>Unsuccessful</answer>"),
    ]
    ctx = cached_context()
    assert grade(ctx).passed
    old_obs = copy.deepcopy(ctx.last_step_output)
    ctx.last_step_output["obs"]["axtree_txt"] = "WATCH HISTORY CLEARED"
    assert not grade(ctx).passed
    ctx.last_step_output = old_obs
    # Returning to old evidence cannot revive the historical successful verdict.
    assert not grade(ctx).passed
    assert client.chat.completions.create.call_count == 3


@pytest.mark.parametrize("error", [RuntimeError("private exception"), "malformed"])
def test_transient_failures_are_not_reused(client, error):
    first = response(error) if isinstance(error, str) else error
    client.chat.completions.create.side_effect = [first, response("<answer>Successful</answer>")]
    ctx = cached_context()
    assert not grade(ctx, max_retries=0).passed
    assert ctx.judge_audits[-1]["reuse"]["status"] == "not_stored_after_error"
    assert grade(ctx, max_retries=0).passed
    assert client.chat.completions.create.call_count == 2


@pytest.mark.parametrize("error", [RuntimeError("private exception"), "malformed"])
def test_repaired_or_pruned_verdict_is_not_reused(client, error):
    first = response(error) if isinstance(error, str) else error
    client.chat.completions.create.side_effect = [
        first, response("<answer>Successful</answer>"), response("<answer>Unsuccessful</answer>"),
    ]
    ctx = cached_context()
    assert grade(ctx).passed
    assert ctx.judge_audits[-1]["reuse"]["status"] == "not_stored_after_error"
    assert not grade(ctx).passed
    assert client.chat.completions.create.call_count == 3


def test_configuration_error_clears_previous_verdict(client):
    client.chat.completions.create.side_effect = [
        response("<answer>Successful</answer>"), response("<answer>Unsuccessful</answer>"),
    ]
    ctx = cached_context()
    assert grade(ctx).passed
    assert not grade(ctx, sampling={"temperature": -1}).passed
    assert ctx.judge_audits[-1]["status"] == "configuration_error"
    assert not grade(ctx).passed
    assert client.chat.completions.create.call_count == 2


@pytest.mark.parametrize("policy", ["env", "node"])
def test_disabling_reuse_records_fresh_samples(client, monkeypatch, policy):
    client.chat.completions.create.side_effect = [
        response("<answer>Successful</answer>"), response("<answer>Unsuccessful</answer>"),
    ]
    ctx = cached_context()
    config = {"reuse": "none"} if policy == "node" else {}
    if policy == "env":
        monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_REUSE", "none")
    assert grade(ctx, **config).passed
    assert not grade(ctx, **config).passed
    assert ctx.judge_audits[-1]["reuse"] == {"policy": "none", "status": "disabled"}
    assert client.chat.completions.create.call_count == 2


def test_node_policy_overrides_environment(client, monkeypatch):
    client.chat.completions.create.return_value = response("<answer>Successful</answer>")
    monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_REUSE", "none")
    ctx = cached_context()
    assert grade(ctx, reuse="identical_input").passed
    assert grade(ctx, reuse="identical_input").passed
    assert client.chat.completions.create.call_count == 1


@pytest.mark.parametrize("missing", ["observation", "screenshot", "unsupported"])
def test_incomplete_evidence_does_not_reuse_old_verdict(client, missing):
    client.chat.completions.create.side_effect = [
        response("<answer>Successful</answer>"), response("<answer>Unsuccessful</answer>"),
    ]
    ctx = cached_context()
    assert grade(ctx).passed
    if missing == "observation":
        ctx.last_step_output = None
        expected = "missing_current_observation"
    elif missing == "screenshot":
        ctx.last_step_output["obs"]["screenshot"] = object()
        expected = "unencoded_screenshot"
    else:
        ctx.baselines["unsupported"] = object()
        expected = "unsupported_evidence"
    assert not grade(ctx).passed
    assert ctx.judge_audits[-1]["reuse"]["status"] == expected
    assert client.chat.completions.create.call_count == 2


def test_new_execution_scope_never_reuses_verdict(client):
    client.chat.completions.create.side_effect = [
        response("<answer>Successful</answer>"), response("<answer>Unsuccessful</answer>"),
    ]
    first, second = cached_context(), cached_context()
    assert first.judge_cache.scope_id != second.judge_cache.scope_id
    assert grade(first).passed
    assert not grade(second).passed


def test_replay_of_cached_hit_uses_frozen_original_request_and_new_calls(client):
    client.chat.completions.create.return_value = response("<answer>Successful</answer>")
    ctx = cached_context()
    grade(ctx)
    grade(ctx)
    hit = ctx.judge_audits[-1]
    client.chat.completions.create.reset_mock()
    replay = judge_audit.replay_audit(hit, repeats=2)
    assert client.chat.completions.create.call_count == 2
    assert replay["source_audit_id"] == hit["audit_id"]
    assert replay["submitted_audit_id"] == hit["reuse"]["source_audit_id"]
    assert replay["agreement"]["samples"] == 2
    assert client.chat.completions.create.call_args.kwargs == hit["source_audit"]["attempts"][0]["request"]


@pytest.mark.parametrize("task_id,expected_score", [("112", 0.5), ("344", 2 / 3)])
def test_legacy_reported_task_dags_keep_reuse_and_dependency_provenance(client, monkeypatch, task_id, expected_score):
    raw = legacy_task(task_id)  # Archived strategies retain cache regression coverage.
    # Only the fallback is under test; do not issue real backend HTTP calls.
    import webarena_pro_core.eval.dag as dag_module
    original = dag_module.get_node_evaluator
    monkeypatch.setattr(dag_module, "get_node_evaluator", lambda kind:
        SimpleNamespace(evaluate=lambda *_: NodeResult(False, "fixture: backend unavailable", True))
        if kind == "backend_state" else original(kind))
    evaluator = DAGEvaluator(parse_eval_dag(raw["eval"]))
    ctx = cached_context()
    ctx.task_config = raw
    count = len(raw["eval"]["nodes"])
    client.chat.completions.create.side_effect = [
        *[response("<answer>Successful</answer>") for _ in range(count - 1)],
        response("<answer>Unsuccessful</answer>"),
        *[response("<answer>Unsuccessful</answer>") for _ in range(count)],
    ]
    score, first = evaluator.evaluate(ctx)
    assert score == expected_score
    score, repeated = evaluator.evaluate(ctx)
    assert score == expected_score
    assert client.chat.completions.create.call_count == count
    for node_id, result in repeated.items():
        audit = result["judge_audits"][0]
        assert audit["node_id"] == node_id
        assert audit["reuse"]["source_audit_id"] == first[node_id]["judge_audits"][0]["audit_id"]
    ctx.last_step_output["obs"]["axtree_txt"] = "Completed action has been undone"
    score, reversed_state = evaluator.evaluate(ctx)
    assert score == 0
    if task_id == "344":
        assert reversed_state["r2"]["reason"] == "dependency failed: r1"
        assert "judge_audits" not in reversed_state["r2"]
        assert "r1" in reversed_state["r3"]["reason"]



def _fallback_dag():
    return DAGEvaluator(parse_eval_dag({"nodes": [{
        "id": "saved", "type": "tiered", "eval_config": {"strategies": [
            {"tier": 0, "type": "backend_state", "trust": "pass_only", "config": {}},
            {"tier": 2, "type": "llm_judge", "config": {"rubric": "File saved"}},
        ]},
    }]}))


def test_current_fallback_probe_conditions_invalidate_cached_verdict(client, monkeypatch):
    import webarena_pro_core.eval.dag as dag_module
    probes = iter([NodeResult(False, "HTTP 503", True), NodeResult(False, "file absent")])
    original = dag_module.get_node_evaluator
    monkeypatch.setattr(dag_module, "get_node_evaluator", lambda kind:
        SimpleNamespace(evaluate=lambda *_: next(probes)) if kind == "backend_state" else original(kind))
    client.chat.completions.create.side_effect = [
        response("<answer>Successful</answer>"), response("<answer>Unsuccessful</answer>"),
    ]
    ctx = cached_context()
    dag = _fallback_dag()
    assert dag.evaluate(ctx)[0] == 1
    assert dag.evaluate(ctx)[0] == 0
    assert client.chat.completions.create.call_count == 2


def test_authoritative_intervening_result_discards_previous_fallback(client, monkeypatch):
    import webarena_pro_core.eval.dag as dag_module
    probes = iter([NodeResult(False, "not matched"), NodeResult(True, "file saved"),
                   NodeResult(False, "not matched")])
    original = dag_module.get_node_evaluator
    monkeypatch.setattr(dag_module, "get_node_evaluator", lambda kind:
        SimpleNamespace(evaluate=lambda *_: next(probes)) if kind == "backend_state" else original(kind))
    client.chat.completions.create.side_effect = [
        response("<answer>Successful</answer>"), response("<answer>Unsuccessful</answer>"),
    ]
    ctx = cached_context()
    dag = _fallback_dag()
    assert dag.evaluate(ctx)[0] == 1
    score, middle = dag.evaluate(ctx)
    assert score == 1 and "judge_audits" not in middle["saved"]
    assert dag.evaluate(ctx)[0] == 0
    assert client.chat.completions.create.call_count == 2


def test_dependency_skip_discards_previous_child_verdict(client, monkeypatch):
    import webarena_pro_core.eval.dag as dag_module
    probes = iter([NodeResult(True), NodeResult(False), NodeResult(True)])
    original = dag_module.get_node_evaluator
    monkeypatch.setattr(dag_module, "get_node_evaluator", lambda kind:
        SimpleNamespace(evaluate=lambda *_: next(probes)) if kind == "backend_state" else original(kind))
    client.chat.completions.create.side_effect = [
        response("<answer>Successful</answer>"), response("<answer>Unsuccessful</answer>"),
    ]
    dag = DAGEvaluator(parse_eval_dag({"nodes": [
        {"id": "parent", "type": "backend_state"},
        {"id": "child", "type": "llm_judge", "depends_on": ["parent"], "eval_config": {"rubric": "child"}},
    ]}))
    ctx = cached_context()
    assert dag.evaluate(ctx)[0] == 1
    assert dag.evaluate(ctx)[1]["child"]["reason"] == "dependency failed: parent"
    assert dag.evaluate(ctx)[0] == 0
    assert client.chat.completions.create.call_count == 2



def test_unsupported_context_evidence_bypasses_cache_without_breaking_dag(client):
    client.chat.completions.create.return_value = response("<answer>Successful</answer>")
    ctx = cached_context()
    ctx.baselines["unknown"] = object()
    dag = DAGEvaluator(parse_eval_dag({"nodes": [
        {"id": "saved", "type": "llm_judge", "eval_config": {"rubric": "Save file"}},
    ]}))
    for _ in range(2):
        score, results = dag.evaluate(ctx)
        assert score == 1
        assert results["saved"]["judge_audits"][0]["reuse"]["status"] == "unsupported_evidence"
    assert client.chat.completions.create.call_count == 2


@pytest.mark.parametrize("policy", ["none", "identical_input"])
@pytest.mark.parametrize("task_id,initial", [("112", 0.5), ("344", 2 / 3)])
def test_legacy_scripted_score_pattern_is_stable_only_for_identical_inputs(client, monkeypatch, policy, task_id, initial):
    """This is a controlled flip sequence, not a reproduction of a real model."""
    import webarena_pro_core.eval.dag as dag_module
    raw = legacy_task(task_id)
    original = dag_module.get_node_evaluator
    monkeypatch.setattr(dag_module, "get_node_evaluator", lambda kind:
        SimpleNamespace(evaluate=lambda *_: NodeResult(False, "fixture", True))
        if kind == "backend_state" else original(kind))
    monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_REUSE", policy)
    votes = ([True, False, False, False, True, False] if task_id == "112"
             else [True, True, False, False, True, True, False])
    client.chat.completions.create.side_effect = [
        response("<answer>Successful</answer>" if vote else "<answer>Unsuccessful</answer>")
        for vote in votes
    ]
    ctx = cached_context()
    ctx.task_config = raw
    dag = DAGEvaluator(parse_eval_dag(raw["eval"]))
    scores = [dag.evaluate(ctx)[0] for _ in range(3)]
    assert scores == ([initial, 0, initial] if policy == "none" else [initial] * 3)
    expected_calls = len(votes) if policy == "none" else len(raw["eval"]["nodes"])
    assert client.chat.completions.create.call_count == expected_calls


def test_semantic_ui_changes_invalidate_but_capture_metadata_does_not(client):
    from webarena_pro_core.eval.ui_evidence import UIEvidence, UIEvidencePlan, UIProbe, UIProbeResult

    client.chat.completions.create.side_effect = [
        response("<answer>Successful</answer>"), response("<answer>Unsuccessful</answer>"),
    ]
    ctx = cached_context()
    probe = UIProbe(kind="count", selector=".target")
    ctx.last_step_output["obs"]["url"] = "http://fixture/"

    def capture(count, time):
        return UIEvidence(
            evaluation_id=f"capture-{time}", captured_at=float(time), step=time,
            url=ctx.last_step_output["obs"]["url"], status="ok",
            plan_sha256=UIEvidencePlan(probes=[probe]).sha256,
            results={probe.key: UIProbeResult(probe=probe, status="ok", count=count)},
        )

    ctx.ui_evidence = capture(1, 1)
    assert grade(ctx).passed
    ctx.ui_evidence = capture(1, 2)
    assert grade(ctx).passed
    assert client.chat.completions.create.call_count == 1
    ctx.ui_evidence = capture(0, 3)
    assert not grade(ctx).passed
    assert client.chat.completions.create.call_count == 2
