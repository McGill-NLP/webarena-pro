"""Trust policy regressions: semantic misses vs authoritative state failures."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from webarena_pro_core.eval import dag
from webarena_pro_core.eval.answer_match import AnswerMatchEvaluator
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, NodeResult, parse_eval_dag
from webarena_pro_core.eval.tiered import TieredRubricEvaluator, _DEFAULT_TRUST

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "webarena-pro-core/src/webarena_pro_core/config"
TASKS = {task["task_id"]: task for path in CONFIG.glob("*.raw.json")
         for task in json.loads(path.read_text())}


@pytest.mark.parametrize("kind", ["answer_match", "backend_state"])
@pytest.mark.parametrize("trust", [None, "both", "pass_only"])
@pytest.mark.parametrize("first", ["pass", "fail", "inconclusive", "error"])
def test_t0_trust_reachability_and_provenance(monkeypatch, kind, trust, first):
    calls = []
    def probe(config, context):
        if first == "error":
            raise RuntimeError("test probe unavailable")
        return NodeResult(first == "pass", "observed condition", first == "inconclusive")
    def fallback(config, context):
        calls.append("judge")
        return NodeResult(True, "semantic evidence")
    monkeypatch.setitem(dag._REGISTRY, kind, SimpleNamespace(evaluate=probe))
    monkeypatch.setitem(dag._REGISTRY, "llm_judge", SimpleNamespace(evaluate=fallback))
    strategy = {"tier": 0, "type": kind, "config": {}}
    if trust is not None:
        strategy["trust"] = trust
    result = TieredRubricEvaluator().evaluate({"strategies": [strategy,
        {"tier": 2, "type": "llm_judge", "config": {}}]}, EvalContext())
    expected_fallback = first in {"inconclusive", "error"} or (first == "fail" and trust == "pass_only")
    assert bool(calls) == expected_fallback
    assert result.passed == (first == "pass" or expected_fallback)
    assert f"trust={trust or 'both'}, source={'explicit' if trust else 'default'}" in result.reason


def test_t1_miss_reaches_judge_after_heuristic_t0_miss(monkeypatch):
    calls = []
    for kind, passed in [("answer_match", False), ("browser_event", False), ("llm_judge", True)]:
        def evaluate(config, context, kind=kind, passed=passed):
            calls.append(kind)
            return NodeResult(passed)
        monkeypatch.setitem(dag._REGISTRY, kind, SimpleNamespace(evaluate=evaluate))
    result = TieredRubricEvaluator().evaluate({"strategies": [
        {"tier": 0, "type": "answer_match", "trust": "pass_only"},
        {"tier": 1, "type": "browser_event"}, {"tier": 2, "type": "llm_judge"},
    ]}, EvalContext())
    assert result.passed
    assert calls == ["answer_match", "browser_event", "llm_judge"]


@pytest.mark.parametrize("answer,judge_pass", [
    ("**Payment Gateway** (v3.2.1), owned by **Charlie**", True),
    ("Payment Gateway v3.2.1, owned by Alice", False),
    ("Search Service v3.2.1, owned by Charlie", False),
    ("It is not Payment Gateway v3.2.1 or Charlie", False),
])
def test_task099_uses_semantic_fallback_for_formatted_and_wrong_answers(monkeypatch, answer, judge_pass):
    calls = []
    def judge(config, context):
        calls.append(config)
        return NodeResult(judge_pass, "scripted verdict")
    monkeypatch.setitem(dag._REGISTRY, "llm_judge", SimpleNamespace(evaluate=judge))
    task = TASKS["099"]
    context = EvalContext(task_config=task, last_action=f"send_msg_to_user({answer!r})")
    score, results = DAGEvaluator(parse_eval_dag(task["eval"])).evaluate(context)
    assert score == float(judge_pass)
    assert len(calls) == 1
    assert "Tuesday" in calls[0]["rubric"] and "Charlie" in calls[0]["rubric"]
    assert "T0:answer_match=FAIL" in results["r1"]["reason"]
    assert "trust=pass_only, source=explicit" in results["r1"]["reason"]


def test_task099_narrow_fast_path_skips_judge(monkeypatch):
    def unexpected(*args):
        pytest.fail("canonical answer must not call judge")
    monkeypatch.setitem(dag._REGISTRY, "llm_judge", SimpleNamespace(evaluate=unexpected))
    task = TASKS["099"]
    score, _ = DAGEvaluator(parse_eval_dag(task["eval"])).evaluate(
        EvalContext(task_config=task, last_action="send_msg_to_user('Payment Gateway v3.2.1; Charlie')"))
    assert score == 1.0


@pytest.mark.parametrize("task_id,node_id,answer", [
    ("045", "r1", "187845.95"),
    ("126", "r2", "Memory Foam Mattress costs $499.99"),
])
def test_prompt_mandated_formats_keep_authoritative_failures(monkeypatch, task_id, node_id, answer):
    def unexpected(*args):
        pytest.fail("authoritative failure cannot reach judge")
    monkeypatch.setitem(dag._REGISTRY, "llm_judge", SimpleNamespace(evaluate=unexpected))
    node = next(n for n in TASKS[task_id]["eval"]["nodes"] if n["id"] == node_id)
    result = TieredRubricEvaluator().evaluate(node["eval_config"], EvalContext(last_action=f"send_msg_to_user({answer!r})"))
    assert not result.passed
    assert "trust=both, source=explicit" in result.reason


def test_audit_reports_conditional_fallbacks_and_matches_runtime_defaults():
    spec = importlib.util.spec_from_file_location("audit_evaluator_trust", ROOT / "webarena-pro-core/scripts/audit_evaluator_trust.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DEFAULT_TRUST == _DEFAULT_TRUST
    rows = module.audit(CONFIG)
    assert {r["split"] for r in rows} == {"test", "dev"}
    task099 = next(r for r in rows if (r["task_id"], r["node_id"]) == ("099", "r1"))
    assert task099["concrete_failure_escalates"] and task099["trust_source"] == "explicit"
    strict = next(r for r in rows if (r["task_id"], r["node_id"]) == ("126", "r2"))
    assert strict["conditional_fallback"] and not strict["concrete_failure_escalates"]
    assert not any(r["invalid_trust"] for r in rows)

@pytest.mark.parametrize("task_id,node_id", [
    ("159", "r1"), ("159", "r4"), ("165", "r1"), ("165", "r4"),
    ("176", "r1"), ("176", "r2"), ("176", "r3"), ("176", "r4"),
])
@pytest.mark.parametrize("saved_state_matches", [False, True])
def test_incomplete_nextcloud_probes_cannot_bypass_saved_state_judging(
    monkeypatch, task_id, node_id, saved_state_matches
):
    # Model the old misleading observations: a matching title, three arbitrary
    # files, or an unrelated existing room. None proves the requested action.
    def incomplete_probe(config, context):
        return NodeResult(True, "matching title/count/action only")

    calls = []
    def judge(config, context):
        calls.append(config)
        return NodeResult(saved_state_matches, "scripted saved-state verdict")

    for kind in ("backend_state", "browser_event"):
        monkeypatch.setitem(dag._REGISTRY, kind, SimpleNamespace(evaluate=incomplete_probe))
    monkeypatch.setitem(dag._REGISTRY, "nextcloud_saved_state", SimpleNamespace(
        evaluate=lambda config, context: NodeResult(False, "saved evidence unavailable", inconclusive=True)
    ))
    monkeypatch.setitem(dag._REGISTRY, "llm_judge", SimpleNamespace(evaluate=judge))
    task = TASKS[task_id]
    node = next(n for n in task["eval"]["nodes"] if n["id"] == node_id)
    result = TieredRubricEvaluator().evaluate(node["eval_config"], EvalContext(task_config=task))
    assert result.passed is saved_state_matches
    assert len(calls) == 1
