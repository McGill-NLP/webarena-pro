"""Missing list entries and malformed paths have different evaluation semantics."""

import json
from pathlib import Path

import pytest
import requests

from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import EvalContext, NodeResult, get_node_evaluator
from webarena_pro_core.eval.tiered import TieredRubricEvaluator


def response(payload):
    result = requests.Response()
    result.status_code = 200
    result._content = json.dumps(payload).encode()
    return result


@pytest.mark.parametrize("payload,path", [
    ({"playlists": []}, "playlists.0.user_id"),
    ({"playlists": [{"user_id": "aciduser"}]}, "playlists.1.user_id"),
    ({"playlists": [["one"]]}, "playlists.0.2"),
])
@pytest.mark.parametrize("operator,expected", [("exists", False), ("equals", False), ("not_exists", True)])
def test_missing_list_index_is_a_condition_result(payload, path, operator, expected):
    check = {"type": "json_path", "path": path, "operator": operator, "value": "aciduser"}
    actual, reason = BackendStateEvaluator()._run_check(check, response(payload))
    assert actual is expected
    assert "missing (index" in reason and "list length" in reason
    assert BackendStateEvaluator._check_json_path(check, response(payload)) is expected


@pytest.mark.parametrize("path", ["playlists.-1.user_id", "playlists.+1.user_id", "playlists.first.user_id",
                                    "playlists.².user_id", "playlists..user_id", ""])
def test_invalid_index_forms_are_inconclusive_configuration_errors(monkeypatch, path):
    monkeypatch.setattr(requests, "request", lambda **kw: response({"playlists": [{"user_id": "aciduser"}, []]}))
    result = BackendStateEvaluator().evaluate({
        "url": "http://fixture/state", "checks": [{"type": "json_path", "path": path, "operator": "not_exists"}],
    }, EvalContext())
    assert not result.passed and result.inconclusive
    assert "invalid JSON path" in result.reason


@pytest.mark.parametrize("operator,value", [("equals", "aciduser"), ("contains", "acid"), ("exists", None)])
def test_nested_valid_index_keeps_existing_operators(operator, value):
    check = {"path": "playlists.0.user_id", "operator": operator, "value": value}
    assert BackendStateEvaluator._check_json_path(check, response({"playlists": [{"user_id": "aciduser"}]}))


def test_task_335_empty_playlists_follows_configured_fallback(monkeypatch):
    config = Path(__file__).parents[1] / "src/webarena_pro_core/config/acidwave.raw.json"
    task = next(task for task in json.loads(config.read_text()) if task["task_id"] == "335")
    rubric = task["eval"]["nodes"][0]["eval_config"]
    monkeypatch.setenv("WP_EVAL_TOKEN", "test-token")
    monkeypatch.setattr(requests, "request", lambda **kw: response({"playlists": []}))
    monkeypatch.setattr(get_node_evaluator("llm_judge"), "evaluate",
                        lambda *a: NodeResult(passed=False, reason="no playlist was saved"))
    probe = BackendStateEvaluator().evaluate(rubric["strategies"][0]["config"], EvalContext(task_config=task))
    assert not probe.passed and not probe.inconclusive
    assert "playlists.0 missing (index 0, list length 0)" in probe.reason
    result = TieredRubricEvaluator().evaluate(rubric, EvalContext(task_config=task))
    assert not result.passed
    assert "IndexError" not in result.reason and "INCONCLUSIVE" not in result.reason
    assert "no playlist was saved" in result.reason


def test_unrelated_json_implementation_error_is_not_reported_as_a_missing_value():
    class BrokenResponse:
        def json(self):
            raise RuntimeError("unexpected response implementation failure")

    with pytest.raises(RuntimeError, match="unexpected response implementation failure"):
        BackendStateEvaluator._check_json_path({"path": "playlists.0", "operator": "not_exists"},
                                              BrokenResponse())
