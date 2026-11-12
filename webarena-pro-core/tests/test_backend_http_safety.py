"""HTTP errors are unavailable evidence, never evidence of an empty dataset."""

import json
from pathlib import Path

import pytest
import requests

from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import EvalContext, NodeResult, get_node_evaluator
from webarena_pro_core.eval.tiered import TieredRubricEvaluator


def response(payload=None, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload if payload is not None else {}).encode()
    return result


@pytest.mark.parametrize("status", [301, 401, 403, 404, 500, 503])
@pytest.mark.parametrize("check", [
    {"type": "count_occurrences", "pattern": '"checksum"', "operator": "eq", "value": 0},
    {"type": "body_not_contains", "value": "2015"},
    {"type": "json_path", "path": "assets", "operator": "not_exists"},
])
def test_error_body_cannot_prove_absence(monkeypatch, status, check):
    monkeypatch.setattr(requests, "request", lambda **kw: response({"error": "unavailable"}, status))
    result = BackendStateEvaluator().evaluate(
        {"url": "http://fixture/state", "checks": [check]}, EvalContext()
    )
    assert not result.passed and result.inconclusive
    assert f"GET http://fixture/state → {status}" in result.reason
    assert "content checks skipped" in result.reason


@pytest.mark.parametrize("expected", [404, [404, 410]])
def test_explicit_non_success_status_allows_intentional_content_checks(monkeypatch, expected):
    monkeypatch.setattr(requests, "request", lambda **kw: response({"error": "deleted"}, 404))
    result = BackendStateEvaluator().evaluate(
        {"url": "http://fixture/state", "checks": [
            {"type": "body_contains", "value": "deleted"},
            {"type": "status_code", "expected": expected},
        ]}, EvalContext(),
    )
    assert result.passed and not result.inconclusive


def test_explicit_non_success_status_does_not_accept_other_errors(monkeypatch):
    monkeypatch.setattr(requests, "request", lambda **kw: response({}, 503))
    result = BackendStateEvaluator().evaluate(
        {"url": "http://fixture/state", "checks": [{"type": "status_code", "expected": 404}]},
        EvalContext(),
    )
    assert not result.passed and result.inconclusive


def test_success_response_that_does_not_match_expected_status_is_definitive(monkeypatch):
    monkeypatch.setattr(requests, "request", lambda **kw: response({}, 200))
    result = BackendStateEvaluator().evaluate(
        {"url": "http://fixture/state", "checks": [{"type": "status_code", "expected": 404}]},
        EvalContext(),
    )
    assert not result.passed and not result.inconclusive


def test_failed_lookup_is_inconclusive_and_skips_main_request(monkeypatch):
    requests_seen = []

    def request(**kw):
        requests_seen.append(kw["url"])
        return response({"id": "error-document-id"}, 500)

    monkeypatch.setattr(requests, "request", request)
    result = BackendStateEvaluator().evaluate({
        "url": "http://fixture/main", "resolve": [
            {"url": "http://fixture/lookup", "extract": "id", "bind": "id"},
        ],
    }, EvalContext())
    assert not result.passed and result.inconclusive
    assert requests_seen == ["http://fixture/lookup"]
    assert "resolve requires a successful 2xx" in result.reason


def test_empty_successful_prerequisite_does_not_skip_main_request(monkeypatch):
    requests_seen = []

    def request(**kw):
        requests_seen.append(kw["url"])
        return response({}, 204 if kw["url"].endswith("unlock") else 200)

    monkeypatch.setattr(requests, "request", request)
    result = BackendStateEvaluator().evaluate({
        "url": "http://fixture/state", "resolve": [{"url": "http://fixture/unlock"}],
        "checks": [{"type": "status_code", "expected": 200}],
    }, EvalContext())
    assert result.passed and not result.inconclusive
    assert requests_seen == ["http://fixture/unlock", "http://fixture/state"]


def test_rejected_cached_session_logs_in_and_retries_once(monkeypatch):
    evaluator = BackendStateEvaluator()
    monkeypatch.setenv("WP_IMMICH_URL", "http://fixture")
    evaluator._token_cache[("http://fixture/api/auth/login", "admin@immich.local")] = "expired"
    logins = []
    tokens = []

    def login(url, **kw):
        logins.append((url, kw["json"]["email"]))
        return response({"accessToken": "fresh"})

    def request(**kw):
        tokens.append(kw["headers"]["Authorization"])
        return response({"assets": {"items": []}}, 401 if tokens[-1] == "Bearer expired" else 200)

    monkeypatch.setattr(requests, "post", login)
    monkeypatch.setattr(requests, "request", request)
    result = evaluator.evaluate({"api": "search_metadata", "params": {"body": "{}"}},
                                EvalContext(task_config={"sites": ["immich"]}))
    assert result.passed and not result.inconclusive
    assert tokens == ["Bearer expired", "Bearer fresh"]
    assert logins == [("http://fixture/api/auth/login", "admin@immich.local")]


def test_persistent_auth_rejection_is_bounded_and_inconclusive(monkeypatch):
    attempts = []
    monkeypatch.setattr(requests, "post", lambda *a, **kw: response({"accessToken": "token"}))

    def request(**kw):
        attempts.append(kw["url"])
        return response({}, 401)

    monkeypatch.setattr(requests, "request", request)
    result = BackendStateEvaluator().evaluate({
        "api": "search_metadata", "params": {"body": "{}"},
        "checks": [{"type": "count_occurrences", "pattern": "checksum", "operator": "eq", "value": 0}],
    }, EvalContext(task_config={"sites": ["immich"]}))
    assert not result.passed and result.inconclusive
    assert len(attempts) == 2


def test_login_error_document_cannot_supply_a_session_token(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: response({"accessToken": "bogus"}, 500))
    monkeypatch.setattr(requests, "request", lambda **kw: pytest.fail("main request must not run"))
    result = BackendStateEvaluator().evaluate({"api": "search_metadata", "params": {"body": "{}"}},
                                            EvalContext(task_config={"sites": ["immich"]}))
    assert not result.passed and result.inconclusive
    assert "authentication requires a successful 2xx" in result.reason


def test_unexpected_http_failure_reaches_fallback_with_default_trust(monkeypatch):
    monkeypatch.setattr(requests, "request", lambda **kw: response({}, 401))
    monkeypatch.setattr(get_node_evaluator("llm_judge"), "evaluate",
                        lambda *a: NodeResult(passed=False, reason="no successful deletion evidence"))
    result = TieredRubricEvaluator().evaluate({"strategies": [
        {"type": "backend_state", "config": {
            "url": "http://fixture/state", "checks": [
                {"type": "count_occurrences", "pattern": "checksum", "operator": "eq", "value": 0},
            ],
        }},
        {"type": "llm_judge", "config": {}},
    ]}, EvalContext())
    assert not result.passed
    assert "INCONCLUSIVE" in result.reason
    assert "no successful deletion evidence" in result.reason


def test_all_current_immich_metadata_checks_use_authenticated_search(monkeypatch):
    config = Path(__file__).parents[1] / "src/webarena_pro_core/config/immich.raw.json"
    metadata = []
    for task in json.loads(config.read_text()):
        for node in task["eval"]["nodes"]:
            for strategy in node["eval_config"].get("strategies", []):
                probe = strategy.get("config", {})
                if probe.get("api") == "search_metadata":
                    metadata.append((task, probe))
    assert len(metadata) == 9  # Task 092 preservation now uses the authenticated Immich snapshot provider.
    logins, searches = [], []

    def login(url, **kw):
        logins.append(kw["json"]["email"])
        return response({"accessToken": "valid-admin-session"})

    def request(**kw):
        assert kw["headers"]["Authorization"] == "Bearer valid-admin-session"
        assert kw["auth"] is None
        if kw["url"].endswith("/session/unlock"):
            return response({}, 204)
        searches.append(kw["url"])
        return response({"assets": {"items": []}})

    monkeypatch.setattr(requests, "post", login)
    monkeypatch.setattr(requests, "request", request)
    for task, probe in metadata:
        result = BackendStateEvaluator().evaluate(probe, EvalContext(task_config=task))
        assert not result.inconclusive
    assert len(searches) == len(metadata)
    assert logins == ["admin@immich.local"] * len(metadata)


@pytest.mark.parametrize("status", [404, 410])
def test_missing_resource_with_explicit_status_cannot_fall_through(monkeypatch, status):
    monkeypatch.setattr(requests, "request", lambda **kw: response({}, status))
    monkeypatch.setattr(get_node_evaluator("llm_judge"), "evaluate",
                        lambda *a: pytest.fail("missing file is a definitive failure"))
    result = TieredRubricEvaluator().evaluate({"strategies": [
        {"type": "backend_state", "trust": "both", "config": {
            "api": "file_exists", "params": {"user": "alex", "path": "missing.md"},
            "checks": [
                {"type": "count_occurrences", "pattern": "checksum", "operator": "eq", "value": 0},
                {"type": "status_code", "expected": 200},
            ],
        }},
        {"type": "llm_judge", "config": {}},
    ]}, EvalContext(task_config={"sites": ["nextcloud"]}))
    assert not result.passed and not result.inconclusive
    assert "content checks skipped" in result.reason
    assert f"got {status}, expected 200" in result.reason


@pytest.mark.parametrize("status", [401, 403, 500, 503])
def test_explicit_success_status_does_not_make_auth_or_server_errors_definitive(monkeypatch, status):
    monkeypatch.setattr(requests, "request", lambda **kw: response({}, status))
    result = BackendStateEvaluator().evaluate({
        "url": "http://fixture/state", "checks": [{"type": "status_code", "expected": 200}],
    }, EvalContext())
    assert not result.passed and result.inconclusive


def test_redirect_to_successful_login_page_cannot_prove_empty_dataset():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    visited = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            visited.append(self.path)
            self.send_response(302 if self.path == "/state" else 200)
            if self.path == "/state":
                self.send_header("Location", "/login")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = BackendStateEvaluator().evaluate({
            "url": f"http://127.0.0.1:{server.server_port}/state", "checks": [
                {"type": "count_occurrences", "pattern": "checksum", "operator": "eq", "value": 0},
            ],
        }, EvalContext())
        assert not result.passed and result.inconclusive
        assert visited == ["/state"]
        assert "302" in result.reason
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
