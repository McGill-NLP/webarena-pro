import json
from dataclasses import fields

import pytest
from pydantic import ValidationError

from webarena_pro_core.eval.dag import EvalContext, NodeResult, DAGEvaluator, parse_eval_dag
from webarena_pro_core.eval.structural import UIStateEvaluator, BrowserEventEvaluator
from webarena_pro_core.eval.ui_evidence import (
    UIEvidence, UIProbe, UIProbeResult, UIEvidencePlan, EvidenceUnavailable,
    build_ui_evidence_plan, require_ui_evidence, restore_ui_evidence,
)


def capture(probe=None, **kwargs):
    probe = probe or UIProbe(kind="count", selector=".target")
    values = dict(evaluation_id="capture", step=5, tab_id="0", url="http://fixture/",
                  document_id="document", captured_at=1.0, status="ok",
                  plan_sha256=UIEvidencePlan(probes=[probe]).sha256,
                  results={probe.key: UIProbeResult(probe=probe, status="ok", count=1)})
    values.update(kwargs)
    return UIEvidence(**values)


def test_plan_deduplicates_and_finds_nested_and_dynamic_requirements():
    check = {"method": "element_exists", "selector": "html:visible"}
    cfg = {"nodes": [{"type": "tiered", "eval_config": {"strategies": [
        {"type": "ui_state", "config": {"checks": [check, check]}},
        {"type": "tiered", "config": {"strategies": [
            {"type": "ui_state", "config": {"checks": [{"method": "text_contains", "text": "yes"}]}},
            {"type": "nextcloud_reaction_ui", "config": {}},
        ]}},
    ]}}]}
    plan = build_ui_evidence_plan(cfg)
    assert {p.kind for p in plan.probes} == {"count", "first_text", "nextcloud_reactions"}
    assert len(plan.probes) == 3
    assert plan == UIEvidencePlan.model_validate_json(plan.model_dump_json())


@pytest.mark.parametrize("count,passed", [(0, False), (1, True), (2, True)])
def test_counts_are_facts_and_core_applies_predicates(count, passed):
    probe = UIProbe(kind="count", selector=".target")
    evidence = capture(results={probe.key: UIProbeResult(probe=probe, status="ok", count=count)})
    result = UIStateEvaluator().evaluate({"checks": [{"method": "element_exists", "selector": ".target"}]}, EvalContext(ui_evidence=evidence))
    assert result.passed is passed and not result.inconclusive


@pytest.mark.parametrize("state", ["missing", "error", "stale", "truncated", "unsupported", "wrong_id", "wrong_tab", "wrong_step", "wrong_url", "wrong_version"])
def test_unavailable_capture_never_becomes_a_concrete_failure(state):
    evidence = capture().model_dump()
    ctx = EvalContext(ui_evidence=evidence, evaluation_id="capture", evaluation_step=5, evaluation_tab_id="0")
    key = next(iter(evidence["results"]))
    if state == "missing": evidence["results"] = {}
    elif state in {"error", "stale"}: evidence["status"] = state
    elif state in {"truncated", "unsupported"}: evidence["results"][key]["status"] = state
    elif state == "wrong_id": ctx.evaluation_id = "later-capture"
    elif state == "wrong_tab": ctx.evaluation_tab_id = "1"
    elif state == "wrong_step": ctx.evaluation_step = 6
    elif state == "wrong_url": ctx.last_step_output = {"obs": {"url": "http://other/"}}
    else: evidence["schema_version"] = 999
    result = UIStateEvaluator().evaluate({"checks": [{"method": "element_exists", "selector": ".target"}]}, ctx)
    assert not result.passed and result.inconclusive


def test_text_predicate_and_no_element_are_distinct_from_unavailable_text():
    probe = UIProbe(kind="first_text", selector="body")
    for text, passed in [("Hello world", True), ("", False)]:
        ctx = EvalContext(ui_evidence=capture(results={probe.key: UIProbeResult(probe=probe, status="ok", text=text)}))
        result = UIStateEvaluator().evaluate({"checks": [{"method": "text_contains", "text": "world"}]}, ctx)
        assert result.passed is passed and not result.inconclusive


def test_browser_urls_and_saved_ui_replay_use_only_data():
    ctx = EvalContext()
    restore_ui_evidence(ctx, json.loads(capture().model_dump_json()))
    assert require_ui_evidence(ctx).evaluation_id == "capture"
    assert BrowserEventEvaluator().evaluate({"match": {"url_contains": "fixture"}}, ctx).passed
    assert UIStateEvaluator().evaluate({"checks": [{"method": "element_exists", "selector": ".target"}]}, ctx).passed
    assert "page" not in {field.name for field in fields(EvalContext)}
    old = EvalContext(last_step_output={"obs": {"url": "http://fixture/", "axtree_txt": ".target"}})
    assert BrowserEventEvaluator().evaluate({"match": {"url_contains": "fixture"}}, old).passed
    assert UIStateEvaluator().evaluate({"checks": []}, old).inconclusive


def test_malformed_evidence_is_rejected_and_volatile_capture_fields_are_not_semantics():
    a = capture()
    b = capture(evaluation_id="later", step=6, captured_at=2.0, document_id="reloaded")
    assert a.semantic_data() == b.semantic_data()
    data = a.model_dump()
    data["results"]["wrong-key"] = data["results"].pop(next(iter(data["results"])))
    with pytest.raises(EvidenceUnavailable): require_ui_evidence(EvalContext(ui_evidence=data))
    with pytest.raises(ValidationError): UIProbeResult(probe=UIProbe(kind="count"), status="ok", count=True)
    with pytest.raises(ValidationError): UIProbeResult(probe=UIProbe(kind="count"), status="ok")


def test_captured_ui_keeps_tiered_failure_and_inconclusive_rules(monkeypatch):
    from webarena_pro_core.eval import dag
    calls = []
    monkeypatch.setattr(dag._REGISTRY["llm_judge"], "evaluate", lambda *_: calls.append(1) or NodeResult(True))
    config = {"nodes": [{"id": "ui", "type": "tiered", "eval_config": {"strategies": [
        {"type": "ui_state", "config": {"checks": [{"method": "element_exists", "selector": ".target"}]}},
        {"type": "llm_judge", "config": {}},
    ]}}]}
    _, details = DAGEvaluator(parse_eval_dag(config)).evaluate(EvalContext(ui_evidence=capture()))
    assert details["ui"]["passed"] and not calls
    DAGEvaluator(parse_eval_dag(config)).evaluate(EvalContext())
    assert calls == [1]
