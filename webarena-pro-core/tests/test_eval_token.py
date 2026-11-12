import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
import requests

from webarena_pro_core import website_environment
from webarena_pro_core.eval.api_registry import SITE_API_REGISTRY, resolve_api_template
from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import EvalContext, NodeResult
from webarena_pro_core.eval.tiered import TieredRubricEvaluator
from webarena_pro_core.eval_token import EvalTokenConfigurationError, resolve_eval_token
from webarena_pro_core.splits import load_split_tasks
from webarena_pro_core.task import load_raw_tasks


TOKEN_SITES = sorted(
    site for site, templates in SITE_API_REGISTRY.items()
    if any(spec.get("auth_mode") == "eval_token" for spec in templates.values())
)


def test_default_persists_private_token_across_workers_and_commands(monkeypatch, tmp_path):
    monkeypatch.delenv("WP_EVAL_TOKEN_FILE")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = tmp_path / "webarena-pro" / "eval-token"
    script = (
        "from webarena_pro_core import website_environment; "
        "print(website_environment('x-lite')['WP_EVAL_TOKEN'])"
    )
    # Independent interpreters race on first use, just like spawned workers.
    processes = [
        subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(8)
    ]
    tokens = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stderr.decode()
        tokens.append(stdout.decode().strip())
    assert len(set(tokens)) == 1
    assert len(tokens[0]) >= 32
    assert path.read_text().strip() == tokens[0] == resolve_eval_token()
    assert path.stat().st_mode & 0o777 == 0o600
    assert not list(path.parent.glob(".eval-token-*"))
    # Later commands and prewarm slots retain the same value.
    assert subprocess.check_output([sys.executable, "-c", script]).decode().strip() == tokens[0]
    for slot in ("run-worker0-slot0", "run-worker0-slot1", "another-run"):
        monkeypatch.setenv("WP_EXP_HASH", slot)
        assert website_environment("x-lite")["WP_EVAL_TOKEN"] == tokens[0]


def test_override_takes_precedence_without_replacing_file(monkeypatch):
    original = resolve_eval_token()
    path = Path(os.environ["WP_EVAL_TOKEN_FILE"])
    monkeypatch.setenv("WP_EVAL_TOKEN", "explicit-secret")
    assert resolve_eval_token() == "explicit-secret"
    assert website_environment("x-lite")["WP_EVAL_TOKEN"] == "explicit-secret"
    assert path.read_text().strip() == original
    monkeypatch.delenv("WP_EVAL_TOKEN")
    assert resolve_eval_token() == original


@pytest.mark.parametrize("token", ["", " ", "secret\n", "a b", "\tsecret", "non-ascii-é"])
def test_invalid_override_fails_without_creating_file(monkeypatch, token):
    monkeypatch.setenv("WP_EVAL_TOKEN", token)
    with pytest.raises(EvalTokenConfigurationError, match="eval_token_configuration_error"):
        website_environment("x-lite")
    assert not Path(os.environ["WP_EVAL_TOKEN_FILE"]).exists()


@pytest.mark.parametrize("contents", [b"", b" \n", b"bad token", b"\xff"])
def test_invalid_existing_file_is_not_rotated(contents):
    path = Path(os.environ["WP_EVAL_TOKEN_FILE"])
    path.write_bytes(contents)
    with pytest.raises(EvalTokenConfigurationError):
        resolve_eval_token()
    assert path.read_bytes() == contents


def test_unwritable_config_is_actionable(monkeypatch, tmp_path):
    parent = tmp_path / "not-a-directory"
    parent.write_text("occupied")
    monkeypatch.setenv("WP_EVAL_TOKEN_FILE", str(parent / "token"))
    with pytest.raises(EvalTokenConfigurationError, match="permissions"):
        resolve_eval_token()


def test_non_eval_site_does_not_provision_token():
    website_environment("nextcloud")
    assert not Path(os.environ["WP_EVAL_TOKEN_FILE"]).exists()


@pytest.mark.parametrize("site", TOKEN_SITES)
def test_every_registered_site_matches_evaluator_and_reset(monkeypatch, site):
    from webarena_pro_core import state_reset

    expected = website_environment(site, exp_hash="slot0")["WP_EVAL_TOKEN"]
    captured = []
    evaluator = BackendStateEvaluator()
    monkeypatch.setattr(evaluator, "_make_request", lambda *args: (
        captured.append(args) or SimpleNamespace(status_code=200)
    ))
    context = EvalContext(task_config={"sites": [site]})
    evaluator._send(resolve_api_template(site, "eval_state"), context)
    assert captured[0][3]["X-Eval-Token"] == expected

    # Real reset plumbing, with Docker calls captured and proxy disabled.
    monkeypatch.setattr(state_reset, "uses_subdomain_urls", lambda: False)
    reset_calls = []
    manager = SimpleNamespace(reset_container=lambda **kwargs: reset_calls.append(kwargs))
    state_reset.recreate_site_container(site, exp_hash="slot1", container_manager=manager)
    assert reset_calls[0]["environment"]["WP_EVAL_TOKEN"] == expected


def test_existing_container_with_missing_or_wrong_token_requires_recreate():
    from webarena_pro_core.docker import DockerContainerManager

    manager = DockerContainerManager.__new__(DockerContainerManager)
    expected = website_environment("x-lite")
    for configured, needs_recreate in [(None, True), ("old-token", True), (expected["WP_EVAL_TOKEN"], False)]:
        container = SimpleNamespace(
            reload=lambda: None,
            attrs={"Config": {"Env": [] if configured is None else [f"WP_EVAL_TOKEN={configured}"]}},
        )
        assert manager._container_needs_recreate(
            container=container, image=None, environment=expected,
            ports=None, labels=None, network=None,
        ) is needs_recreate


@pytest.fixture
def token_endpoint():
    token = website_environment("x-lite")["WP_EVAL_TOKEN"]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            authorized = self.headers.get("X-Eval-Token") == token
            self.send_response(200 if authorized else 403)
            self.end_headers()
            self.wfile.write(json.dumps({"bookmarks": ["saved"]} if authorized else {"error": "forbidden"}).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api/eval/state", token
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _config(url, expected="saved"):
    return {
        "url": url, "auth_mode": "eval_token",
        "checks": [{"type": "json_path", "path": "bookmarks.0", "value": expected}],
    }


def _tiered(config):
    return {"strategies": [
        {"tier": 0, "type": "backend_state", "trust": "pass_only", "config": config},
        {"tier": 2, "type": "llm_judge", "config": {}},
    ]}


def test_authenticated_tier_zero_pass_and_unmet_condition(token_endpoint, caplog):
    url, token = token_endpoint
    context = EvalContext(task_config={"sites": ["x-lite"]})
    with caplog.at_level(logging.DEBUG):
        result = TieredRubricEvaluator().evaluate(_tiered(_config(url)), context)
        unmet = BackendStateEvaluator().evaluate(_config(url, "not-saved"), context)
    assert result.passed and "decided_by=T0:backend_state" in result.reason
    assert "escalated" not in result.reason
    assert not unmet.passed and not unmet.inconclusive
    assert "authentication_failed" not in unmet.reason
    assert token not in caplog.text
    assert "<redacted>" in caplog.text


@pytest.mark.parametrize("checks", [[], [{"type": "json_path", "path": "bookmarks", "operator": "not_exists"}]])
def test_auth_failure_cannot_pass_empty_or_absence_checks(monkeypatch, token_endpoint, checks, caplog):
    url, token = token_endpoint
    assert requests.get(url, timeout=5).status_code == 403
    assert requests.get(url, headers={"X-Eval-Token": "wrong-token"}, timeout=5).status_code == 403
    monkeypatch.setenv("WP_EVAL_TOKEN", "wrong-token")
    result = BackendStateEvaluator().evaluate(
        {"url": url, "auth_mode": "eval_token", "checks": checks},
        EvalContext(task_config={"sites": ["x-lite"]}),
    )
    assert not result.passed and result.inconclusive
    assert "eval_token_authentication_failed" in result.reason
    assert "site=x-lite, HTTP 403" in result.reason
    assert "env start" in result.reason
    assert "eval_token_authentication_failed" in caplog.text
    assert token not in caplog.text and "wrong-token" not in caplog.text


@pytest.mark.parametrize("status", [401, 403])
def test_resolve_auth_failure_remains_inconclusive(monkeypatch, status):
    evaluator = BackendStateEvaluator()
    monkeypatch.setattr(evaluator, "_make_request", lambda *args: SimpleNamespace(status_code=status))
    result = evaluator.evaluate({
        "api": "eval_state",
        "resolve": [{"api": "eval_state", "extract": "id", "bind": "id"}],
    }, EvalContext(task_config={"sites": ["x-lite"]}))
    assert result.inconclusive
    assert f"HTTP {status}" in result.reason
    assert "resolve bound nothing" not in result.reason


def test_auth_fallback_retains_cause_in_final_tiered_trace(monkeypatch, token_endpoint):
    from webarena_pro_core.eval import dag

    url, _ = token_endpoint
    monkeypatch.setenv("WP_EVAL_TOKEN", "wrong-token")
    monkeypatch.setitem(dag._REGISTRY, "llm_judge", SimpleNamespace(
        evaluate=lambda *args: NodeResult(passed=True, reason="stub judge passed")
    ))
    config = _tiered(_config(url))
    config["strategies"][0]["trust"] = "both"
    result = TieredRubricEvaluator().evaluate(config, EvalContext(task_config={"sites": ["x-lite"]}))
    assert result.passed
    assert "decided_by=T2:llm_judge [escalated]" in result.reason
    assert "T0:backend_state=INCONCLUSIVE(eval_token_authentication_failed:" in result.reason


def test_invalid_configuration_is_visible_without_http(monkeypatch):
    monkeypatch.setenv("WP_EVAL_TOKEN", "")
    evaluator = BackendStateEvaluator()
    monkeypatch.setattr(evaluator, "_make_request", lambda *args: pytest.fail("must not send HTTP"))
    result = evaluator.evaluate({"api": "eval_state"}, EvalContext(task_config={"sites": ["x-lite"]}))
    assert result.inconclusive
    assert "eval_token_configuration_error" in result.reason


def test_active_and_dev_eval_state_strategies_all_receive_shared_token():
    import webarena_pro_core

    root = Path(webarena_pro_core.__file__).parent / "config"
    expected = resolve_eval_token()
    covered = set()

    def audit(value, site):
        if isinstance(value, list):
            return sum(audit(item, site) for item in value)
        if not isinstance(value, dict):
            return 0
        count = 0
        if value.get("type") == "backend_state":
            config = value.get("config", {})
            if config.get("api", "").startswith("eval_state"):
                target = config.get("site", site)
                assert resolve_api_template(target, config["api"]).get("auth_mode") == "eval_token"
                assert website_environment(target)["WP_EVAL_TOKEN"] == expected
                covered.add(target)
                count += 1
        return count + sum(audit(item, site) for item in value.values())

    active_count = dev_count = 0
    for path in sorted(root.glob("*.raw.json")):
        for task in load_raw_tasks(path):
            if "eval" not in task:
                continue
            count = audit(task["eval"], task["sites"][0])
            active_count += count
    for task in load_split_tasks("dev", root):
        dev_count += audit(task["eval"], task["sites"][0])
    assert active_count > 0 and dev_count > 0
    assert covered == set(TOKEN_SITES)
