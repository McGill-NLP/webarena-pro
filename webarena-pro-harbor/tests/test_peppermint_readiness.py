"""Exercise the actual image/export probes against a cold-start HTTP fixture."""

import os
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path

import pytest
import yaml

from webarena_pro_harbor.cli import select_tasks
from webarena_pro_harbor.export import export_tasks


@pytest.fixture
def readiness_probe(tmp_path):
    task = select_tasks("test", "peppermint", "213")[0]
    export_tasks([task], tmp_path / "tasks", split="test")
    env = tmp_path / "tasks/webarena-pro-test-213/environment"
    services = yaml.safe_load((env / "docker-compose.yaml").read_text())["services"]
    assert services["webarena"]["depends_on"]["peppermint"] == {"condition": "service_healthy"}
    check = services["peppermint"]["healthcheck"]
    assert check["interval"] == "5s" and check["timeout"] == "8s"
    assert check["retries"] == 138 and check["start_period"] == "1s"
    command, script = check["test"]
    assert command == "CMD-SHELL"
    # Compose unescapes $$ before the container shell sees the command.
    script = script.replace("$$", "$")
    packaged = files("webarena_pro_harbor").joinpath("templates/peppermint-healthcheck.sh").read_text()
    image_script = Path(__file__).resolve().parents[2] / "websites/peppermint/scripts/healthcheck.sh"
    assert script == packaged == image_script.read_text()
    return script


@pytest.fixture
def readiness_http():
    state = {"frontend": 200, "api": 401, "paths": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            state["paths"].append(self.path)
            self.send_response(state["api"] if self.path == "/api/v1/auth/check" else state["frontend"])
            self.end_headers()
            self.wfile.write(b"private-response-must-not-be-logged")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", state
    server.shutdown()
    server.server_close()
    thread.join()


def run_probe(script, frontend, api):
    return subprocess.run(
        ["sh", "-c", script.replace("http://${HOSTNAME:-127.0.0.1}:3000", frontend).replace("http://127.0.0.1:5003", api)],
        capture_output=True, text=True, timeout=8,
    )


def test_cold_start_waits_for_api_then_becomes_ready(readiness_probe, readiness_http):
    url, state = readiness_http
    # Reserve a port without listening to model the API's startup refusal.
    with socket.socket() as unopened:
        unopened.bind(("127.0.0.1", 0))
        failed = run_probe(readiness_probe, url, f"http://127.0.0.1:{unopened.getsockname()[1]}")
    assert failed.returncode == 1
    assert "login API not ready (HTTP 000)" in failed.stderr
    assert state["paths"] == ["/"]
    ready = run_probe(readiness_probe, url, url)
    assert ready.returncode == 0
    assert state["paths"][-2:] == ["/", "/api/v1/auth/check"]
    assert ready.stdout == ready.stderr == ""


def test_frontend_probe_follows_the_nextjs_bind_hostname(readiness_probe, readiness_http):
    url, _ = readiness_http
    port = url.rsplit(":", 1)[1]
    script = readiness_probe.replace(":3000/", f":{port}/").replace("http://127.0.0.1:5003", url)
    for hostname, expected in (("127.0.0.2", 1), ("127.0.0.1", 0)):
        result = subprocess.run(
            ["sh", "-c", script], capture_output=True, text=True, timeout=8,
            env={**os.environ, "HOSTNAME": hostname, "http_proxy": "http://127.0.0.1:1", "no_proxy": ""},
        )
        assert result.returncode == expected, result.stderr
        if expected:
            assert "frontend not ready" in result.stderr


@pytest.mark.parametrize("frontend,api,ready,component", [
    (200, 200, True, None), (302, 401, True, None),
    (500, 200, False, "frontend"), (404, 200, False, "frontend"),
    (200, 500, False, "login API"), (200, 404, False, "login API"),
    (200, 302, False, "login API"),
])
def test_readiness_requires_both_components(readiness_probe, readiness_http, frontend, api, ready, component):
    url, state = readiness_http
    state.update(frontend=frontend, api=api)
    result = run_probe(readiness_probe, url, url)
    assert (result.returncode == 0) is ready
    assert "private-response" not in result.stdout + result.stderr
    if not ready:
        assert f"{component} not ready" in result.stderr
