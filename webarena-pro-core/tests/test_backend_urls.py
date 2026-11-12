import json

import pytest
import requests

from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import EvalContext, NodeResult
from webarena_pro_core.eval.tiered import TieredRubricEvaluator


def _response(payload, status=200):
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(payload).encode()
    return response


def test_backend_requests_follow_env_changes_after_import(monkeypatch):
    evaluator = BackendStateEvaluator()
    context = EvalContext(task_config={"sites": ["nextcloud"]})
    requested = []

    def request(method, url, **kwargs):
        requested.append(url)
        if url.endswith("/lookup"):
            return _response({"id": "target"})
        return _response({"found": True})

    monkeypatch.setattr(requests, "request", request)
    for slot in (0, 1, 0, 1):
        primary = f"http://nextcloud--w{slot}.localhost:8080"
        secondary = f"http://mydrive--w{slot}.localhost:8080"
        monkeypatch.setenv("WP_NEXTCLOUD_URL", primary)
        monkeypatch.setenv("WP_MYDRIVE_URL", secondary)
        result = evaluator.evaluate(
            {
                "site": "mydrive",
                "resolve": [{"url": "__MYDRIVE__/lookup", "extract": "id", "bind": "id"}],
                "url": "__MYDRIVE__/state",
                "checks": [{"type": "status_code", "expected": 200}],
            },
            context,
        )
        assert result.passed and not result.inconclusive
        assert requested[-2:] == [f"{secondary}/lookup", f"{secondary}/state"]
        assert secondary in result.reason
        assert evaluator._resolve_url("__NEXTCLOUD__/status", context) == f"{primary}/status"


def test_bearer_login_and_request_use_current_slot(monkeypatch):
    evaluator = BackendStateEvaluator()
    context = EvalContext(task_config={"sites": ["mattermost"]})
    logins = []
    requested = []

    def login(url, **kwargs):
        logins.append(url)
        response = _response({})
        response.headers["Token"] = url
        return response

    def request(method, url, headers, **kwargs):
        requested.append((url, headers["Authorization"]))
        return _response({})

    monkeypatch.setattr(requests, "post", login)
    monkeypatch.setattr(requests, "request", request)
    for slot in (0, 1):
        base = f"http://mattermost--w{slot}.localhost:8080"
        monkeypatch.setenv("WP_MATTERMOST_URL", base)
        evaluator._send(
            {"url": "__MATTERMOST__/api/check", "login_url": "__MATTERMOST__/api/login",
             "auth_mode": "bearer_login", "auth_user": "john.doe"},
            context,
        )
        assert logins[-1] == f"{base}/api/login"
        assert requested[-1] == (f"{base}/api/check", f"Bearer {base}/api/login")
    assert len(logins) == 2


@pytest.mark.parametrize("failure", ["network", "auth", "config"])
def test_fallback_evidence_identifies_resolved_lookup_target(monkeypatch, failure):
    from webarena_pro_core.eval.dag import get_node_evaluator

    base = "http://x-lite--w3.localhost:8080"
    monkeypatch.setenv("WP_X_LITE_URL", base)
    monkeypatch.setenv("WP_EVAL_TOKEN", "" if failure == "config" else "test-token")

    def request(*args, **kwargs):
        if failure == "network":
            raise requests.ConnectionError("standby unavailable")
        return _response({}, status=403)

    monkeypatch.setattr(requests, "request", request)
    monkeypatch.setattr(
        get_node_evaluator("llm_judge"), "evaluate",
        lambda *args: NodeResult(passed=True, reason="judge fallback"),
    )
    result = TieredRubricEvaluator().evaluate(
        {"rubric": "check state", "strategies": [{
            "type": "backend_state",
            "config": {"resolve": [{
                "url": "__X-LITE__/lookup", "auth_mode": "eval_token",
                "bind": "id", "extract": "id",
            }], "url": "__X-LITE__/main"},
        }, {"type": "llm_judge", "config": {"rubric": "check state"}}]},
        EvalContext(task_config={"sites": ["x-lite"]}),
    )
    assert result.passed
    assert f"GET {base}/lookup" in result.reason
    assert "INCONCLUSIVE" in result.reason
    assert {"network": "ConnectionError", "auth": "HTTP 403",
            "config": "eval_token_configuration_error"}[failure] in result.reason
    assert "test-token" not in result.reason


def test_pass_only_http_failure_keeps_target_and_status_in_judge_trail(monkeypatch):
    from webarena_pro_core.eval.dag import get_node_evaluator

    base = "http://nextcloud--w3.localhost:8080"
    monkeypatch.setenv("WP_NEXTCLOUD_URL", base)
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: _response({}, 404))
    monkeypatch.setattr(
        get_node_evaluator("llm_judge"), "evaluate",
        lambda *args: NodeResult(passed=True, reason="judge fallback"),
    )
    result = TieredRubricEvaluator().evaluate(
        {"strategies": [
            {"type": "backend_state", "trust": "pass_only", "config": {
                "url": "__NEXTCLOUD__/state",
                "checks": [{"type": "status_code", "expected": 200}],
            }},
            {"type": "llm_judge", "config": {}},
        ]}, EvalContext(task_config={"sites": ["nextcloud"]}),
    )
    assert result.passed
    assert f"GET {base}/state → 404" in result.reason
    assert "got 404, expected 200" in result.reason
