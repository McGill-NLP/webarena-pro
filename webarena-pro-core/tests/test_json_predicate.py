"""Shared JSON checks join records, preserve ordering, and distinguish evidence gaps."""
import copy
import json

import pytest
import requests

from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import EvalContext


def ref(path):
    return {"ref": path}


def compare(op, left, right):
    return {op: [left, right]}


def check():
    return {
        "type": "json_predicate",
        "guards": [{"label": "supported schema", "predicate": compare("eq", ref("data.version"), 1)},
                   {"label": "execution start", "predicate": compare("type", ref("context.task_start_time_ms"), "integer")}],
        "bindings": [{"name": "requests", "value": {"query": {
            "from": ref("data.requests"), "as": "request",
            "where": compare("gte", ref("request.created"), ref("context.task_start_time_ms")),
        }}}, {"name": "latest_approved", "value": {"query": {
            "from": ref("requests"), "as": "request",
            "where": compare("eq", ref("request.approved"), True), "take": "last",
        }}}],
        "predicate": {"some": {
            "from": ref("data.shipments"), "as": "shipment", "where": {"all": [
                compare("eq", ref("shipment.status"), "delivered"),
                {"some": {"from": ref("latest_approved"), "as": "request", "where": {"all": [
                    compare("eq", ref("request.id"), ref("shipment.request_id")),
                    compare("eq", ref("request.sku"), ref("shipment.sku")),
                    compare("gte", ref("request.total"), 10), compare("lte", ref("request.total"), 20),
                ]}}},
            ]},
        }},
    }


def state():
    return {"version": 1, "requests": [
        {"id": "old", "sku": "B", "total": 15, "approved": True, "created": 99},
        {"id": "current", "sku": "A", "total": 15, "approved": True, "created": 100},
        {"id": "draft", "sku": "C", "total": 15, "approved": False, "created": 101},
    ], "shipments": [{"request_id": "current", "sku": "A", "status": "delivered"}]}


def grade(monkeypatch, data, assertion=None, context=None):
    result = requests.Response()
    result.status_code = 200
    result._content = json.dumps(data).encode()
    evaluator = BackendStateEvaluator()
    monkeypatch.setattr(evaluator, "_send", lambda *args: result)
    return evaluator.evaluate({"url": "http://example.test/state", "checks": [assertion or check()]},
                              context or EvalContext(task_start_time_ms=100))


def test_correlated_latest_records_and_undo_use_current_state(monkeypatch):
    data = state()
    result = grade(monkeypatch, data)
    assert result.passed and "evidence_sha256=" in result.reason
    # An older approved request must not replace the latest approved request.
    data["requests"].append({"id": "new", "sku": "B", "total": 15, "approved": True, "created": 102})
    result = grade(monkeypatch, data)
    assert not result.passed and not result.inconclusive
    data["shipments"].append({"request_id": "new", "sku": "B", "status": "delivered"})
    assert grade(monkeypatch, data).passed
    data["shipments"][-1]["status"] = "cancelled"
    result = grade(monkeypatch, data)
    assert not result.passed and not result.inconclusive
    data["shipments"].clear()
    assert not grade(monkeypatch, data).passed


def test_cross_record_matches_cannot_supply_each_others_fields(monkeypatch):
    data = state()
    data["shipments"] = [{"request_id": "current", "sku": "B", "status": "delivered"},
                         {"request_id": "old", "sku": "A", "status": "delivered"}]
    result = grade(monkeypatch, data)
    assert not result.passed and not result.inconclusive


@pytest.mark.parametrize("total,expected", [(9, False), (10, True), (20, True), (21, False)])
def test_inclusive_numeric_range(monkeypatch, total, expected):
    data = state()
    data["requests"][1]["total"] = total
    result = grade(monkeypatch, data)
    assert result.passed == expected and not result.inconclusive


@pytest.mark.parametrize("failure", ["version", "missing_start", "source", "missing_field", "number", "later_bad_row"])
def test_unavailable_evidence_is_inconclusive_even_after_a_matching_row(monkeypatch, failure):
    data, context = state(), EvalContext(task_start_time_ms=100)
    if failure == "version":
        data["version"] = 2
    elif failure == "missing_start":
        context.task_start_time_ms = None
    elif failure == "source":
        data["shipments"] = {}
    elif failure == "missing_field":
        del data["requests"][1]["total"]
    elif failure == "number":
        data["requests"][1]["total"] = "15"
    else:
        data["shipments"].append({"status": "delivered"})
    result = grade(monkeypatch, data, context=context)
    assert not result.passed and result.inconclusive


def test_nested_projection_case_normalization_and_bound_values(monkeypatch):
    assertion = {"type": "json_predicate", "bindings": [
        {"name": "items", "value": {"query": {"from": ref("data.groups"), "as": "group",
                                              "select": ref("group.items"), "flatten": True}}},
        {"name": "names", "value": {"query": {"from": ref("items"), "as": "item", "select": {"upper": ref("item.name")}}}},
    ], "predicate": {"all": [compare("in", "ALPHA", ref("names")),
                              compare("eq", {"ref": "data.optional", "default": None}, None),
                              {"not": compare("in", "BETA", ref("names"))}]}}
    assert grade(monkeypatch, {"groups": [{"items": []}, {"items": [{"name": "alpha"}]}]}, assertion).passed
    # A missing required field does not silently become the optional default.
    del assertion["predicate"]["all"][1]["eq"][0]["default"]
    assert grade(monkeypatch, {"groups": []}, assertion).inconclusive is False  # First condition is definitively false.
    assert grade(monkeypatch, {"groups": [{"items": [{"name": "alpha"}]}]}, assertion).inconclusive


@pytest.mark.parametrize("left,right", [(True, 1), ([True], [1]), ({"flag": True}, {"flag": 1}), (1, "1")])
def test_equality_and_membership_do_not_coerce_types(monkeypatch, left, right):
    literal = lambda value: {"literal": value}
    for predicate in [compare("eq", literal(left), literal(right)), compare("in", literal(left), [right])]:
        result = grade(monkeypatch, {}, {"type": "json_predicate", "predicate": predicate})
        assert not result.passed and not result.inconclusive


def test_type_guard_can_make_an_invalid_numeric_value_a_definitive_nonmatch(monkeypatch):
    assertion = {"type": "json_predicate", "predicate": {"all": [
        compare("type", ref("data.value"), "integer"), compare("gt", ref("data.value"), 0),
    ]}}
    for value in [True, "12", None]:
        result = grade(monkeypatch, {"value": value}, assertion)
        assert not result.passed and not result.inconclusive


@pytest.mark.parametrize("fault", ["unknown_operator", "duplicate_binding", "shadowed_alias", "forward_reference", "bad_take", "bad_flatten"])
def test_invalid_query_configuration_is_inconclusive(monkeypatch, fault):
    assertion = copy.deepcopy(check())
    if fault == "unknown_operator":
        assertion["predicate"] = {"typo": []}
    elif fault == "duplicate_binding":
        assertion["bindings"].append(copy.deepcopy(assertion["bindings"][0]))
    elif fault == "shadowed_alias":
        assertion["bindings"][0]["value"]["query"]["as"] = "data"
    elif fault == "forward_reference":
        assertion["bindings"][0]["value"]["query"]["from"] = ref("latest_approved")
    else:
        assertion["bindings"][0]["value"]["query"]["take" if fault == "bad_take" else "flatten"] = "invalid"
    assert grade(monkeypatch, state(), assertion).inconclusive


def test_empty_collections_are_valid_evidence_not_missing_evidence(monkeypatch):
    result = grade(monkeypatch, {"version": 1, "requests": [], "shipments": []})
    assert not result.passed and not result.inconclusive
