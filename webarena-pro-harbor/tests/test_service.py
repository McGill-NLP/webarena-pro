import json
import shutil
import signal
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from webarena_pro_harbor import service
from webarena_pro_harbor.verify import verify


def test_failure_before_config_parse_survives_service_cleanup(tmp_path):
    evidence, diagnostics = tmp_path / "evidence", tmp_path / "service"
    config = tmp_path / "broken.json"
    config.write_text("{broken setup configuration")
    run = subprocess.run([
        sys.executable, "-m", "webarena_pro_harbor.cli", "supervise", "--config", str(config),
        "--directory", str(evidence), "--diagnostics", str(diagnostics),
        "--socket", str(tmp_path / "control.sock"),
    ], capture_output=True, text=True, timeout=15)
    assert run.returncode == 1
    assert not evidence.exists()
    # Harbor copies a stopped service's declared artifact directory before
    # deleting containers. Model that order, then inspect only the host copy.
    collected = tmp_path / "collected"
    shutil.copytree(diagnostics, collected)
    shutil.rmtree(diagnostics)
    result = json.loads((collected / "result.json").read_text())
    assert result["status"] == "setup_error" and result["exit_code"] == 1
    assert result["steps"] == 0 and result["graded"] is False
    assert "rewards" not in result and "JSONDecodeError" in result["error"]
    assert "JSONDecodeError" in (collected / "stderr.log").read_text()
    assert " in serve" in (collected / "stderr.log").read_text()
    with pytest.raises(ValueError, match="did not complete"):
        verify(collected / "result.json", tmp_path / "reward.json")
    assert not (tmp_path / "reward.json").exists()


def test_capture_redacts_both_streams_and_preserves_exit_status(tmp_path, monkeypatch):
    monkeypatch.setenv("WP_HARBOR_EVAL_TOKEN", "private-env-secret")
    script = '''import os,sys
print('UI login attempt 3/3 failed for peppermint: HTTP 500', flush=True)
print('credential='+os.environ['WP_HARBOR_EVAL_TOKEN'], flush=True)
print('https://user:private-userinfo@host/path?key=private-query', flush=True)
print('{"password": "private-json", "authorization": "Bearer private-auth"}', file=sys.stderr, flush=True)
sys.exit(7)
'''
    original = subprocess.Popen
    monkeypatch.setattr(service.subprocess, "Popen", lambda _cmd, **kw: original([sys.executable, "-u", "-c", script], **kw))
    assert service.supervise("unused", tmp_path / "evidence", "unused", 8000, tmp_path / "service") == 7
    content = "\n".join(p.read_text() for p in (tmp_path / "service").iterdir())
    assert "UI login attempt 3/3 failed for peppermint: HTTP 500" in content
    for secret in ("private-env-secret", "private-userinfo", "private-query", "private-json", "private-auth"):
        assert secret not in content
    assert json.loads((tmp_path / "service/status.json").read_text())["exit_code"] == 7
    assert not (tmp_path / "evidence").exists()


def test_health_failures_and_readiness_are_private_and_bounded(tmp_path):
    with socket.socket() as unopened:
        unopened.bind(("127.0.0.1", 0))
        assert service.healthcheck(tmp_path, unopened.getsockname()[1]) == 1
    failure = json.loads((tmp_path / "health.jsonl").read_text())
    assert failure["ready"] is False and "URLError" in failure["error"]
    assert not (tmp_path / "ready.json").exists()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            assert self.path == "/health"
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ready": true}')

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert service.healthcheck(tmp_path, server.server_port) == 0
        assert json.loads((tmp_path / "ready.json").read_text())["ready"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("text,secret", [
    ('password="literal with spaces"', "literal with spaces"),
    ("api_key=tokenvalue", "tokenvalue"),
    ("Authorization: Bearer bearer-value", "bearer-value"),
    ("DEBUG request Cookie: a=b; session=secret2", "secret2"),
    ("Set-Cookie: session=secret2; Path=/; HttpOnly", "secret2"),
    ("Proxy-Authorization: Digest first=one, token=second-secret", "second-secret"),
    ('{"cookie": "a=b; session=secret2"}', "secret2"),
    ('{"refresh_token": "refresh-value"}', "refresh-value"),
    ("http://name:user-password@example.com/page#secret-fragment", "user-password"),
])
def test_redaction_forms(text, secret):
    assert secret not in service.redact(text)


def test_service_signal_is_forwarded_and_recorded(tmp_path):
    harness = tmp_path / "harness.py"
    marker = tmp_path / "started"
    harness.write_text('''import subprocess,sys
from pathlib import Path
from webarena_pro_harbor import service
original = subprocess.Popen
script = "import time; from pathlib import Path; Path(sys.argv[1]).touch(); time.sleep(120)"
script = "import sys; " + script
service.subprocess.Popen = lambda cmd, **kw: original([sys.executable, "-u", "-c", script, sys.argv[2]], **kw)
raise SystemExit(service.supervise("unused", "unused", "unused", 8000, sys.argv[1]))
''')
    process = subprocess.Popen([sys.executable, str(harness), str(tmp_path / "service"), str(marker)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        import time
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        process.send_signal(signal.SIGTERM)
        output = process.communicate(timeout=10)
        assert process.returncode == 143, output
        state = json.loads((tmp_path / "service/status.json").read_text())
        assert state["exit_code"] == -signal.SIGTERM and state["signal"] == signal.SIGTERM
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def test_worker_preserves_original_cause_without_source_or_locals(monkeypatch, capsys):
    async def fail(*_args, **_kwargs):
        try:
            raise ValueError("original API setup error password=private-original")
        except ValueError as exc:
            raise ExceptionGroup("setup failed", [RuntimeError("nested cause")]) from exc

    monkeypatch.setattr("webarena_pro_mcp.server.serve", fail)
    assert service.worker("unused", "unused", "unused", 8000) == 1
    stderr = capsys.readouterr().err
    assert "original API setup error" in stderr and "nested cause" in stderr
    assert "private-original" not in stderr and "raise ValueError" not in stderr
