"""Task 044 must grade the requested note and exact item row together."""
import json
from pathlib import Path
from urllib.parse import parse_qs

import pytest
import requests

from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
from webarena_pro_core.eval.llm_judge import set_llm_judge_hook

CONFIG = Path(__file__).parents[1] / "src/webarena_pro_core/config/erp-next.raw.json"
TASK = next(task for task in json.loads(CONFIG.read_text()) if task["task_id"] == "044")
NODE = TASK["eval"]["nodes"][1]


def test_complete_delivery_note_query_has_exact_same_row_constraints():
    strategies = NODE["eval_config"]["strategies"]
    probes = [s for s in strategies if s["type"] == "backend_state"]
    # A partial customer/name probe used to short-circuit the item check.
    assert len(probes) == 1
    probe = probes[0]
    assert probe["trust"] == "both"
    assert probe["config"]["params"]["doctype"] == "Delivery Note"
    query = parse_qs(probe["config"]["params"]["query"])
    filters = json.loads(query["filters"][0])
    assert ["Delivery Note", "customer_name", "=", "Boreal Retail Partners East Office"] in filters
    assert ["Delivery Note", "naming_series", "=", "MAT-DN-RET-.YYYY.-"] in filters
    assert ["Delivery Note", "set_warehouse", "=", "Goods In Transit - WAC"] in filters
    assert ["Delivery Note", "docstatus", "<", 2] in filters
    # Frappe joins these constraints on one Delivery Note Item alias. Neither
    # a suffixed SKU nor quantity on another item can satisfy this conjunction.
    assert [f for f in filters if f[0] == "Delivery Note Item"] == [
        ["Delivery Note Item", "item_code", "=", "ACOUSTIC-PANEL-120"],
        ["Delivery Note Item", "qty", "=", 1],
        ["Delivery Note Item", "warehouse", "=", "Goods In Transit - WAC"],
    ]
    assert TASK["intent"].endswith("and one acoustic panel.")
    assert "ACOUSTIC-PANEL-120" in NODE["eval_config"]["rubric"]
    assert "ACOUSTIC-PANEL-120" in strategies[-1]["config"]["rubric"]
    assert [(n["id"], n["depends_on"]) for n in TASK["eval"]["nodes"]] == [
        ("r1", []), ("r2", []),
    ]


@pytest.mark.parametrize("rows,expected", [([], 0), ([{"name": "MAT-DN-RET-2026-00001"}], 1)])
def test_complete_native_query_is_authoritative(monkeypatch, rows, expected):
    calls = []
    def send(self, spec, context):
        calls.append(spec)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"data": rows}).encode()
        return response
    monkeypatch.setattr(BackendStateEvaluator, "_send", send)
    judged = []
    def judge(*args):
        judged.append(args)
        return "pass", "must not override definitive native evidence"
    set_llm_judge_hook(judge)
    try:
        dag = parse_eval_dag({"operator": "AND", "nodes": [NODE]})
        score, details = DAGEvaluator(dag).evaluate(EvalContext(task_config=TASK, last_action="done()"))
    finally:
        set_llm_judge_hook(None)
    assert score == expected
    assert len(calls) == 1
    assert not judged
    assert "decided_by=T0:backend_state" in details["r2"]["reason"]
