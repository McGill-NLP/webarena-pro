import threading
import subprocess
import tempfile
from pathlib import Path
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


@contextmanager
def site_server():
    state = {"saved": False, "private_hits": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path in {"/data.json", "/plain.txt", "/missing-page"}:
                body = b'{"items":[]}' if self.path == "/data.json" else b'No media here'
                self.send_response(404 if self.path == "/missing-page" else 200)
                self.send_header("Content-Type", "application/json" if self.path == "/data.json" else "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/report-redirect":
                self.send_response(302)
                self.send_header("Location", "/report")
                self.end_headers()
                return
            if self.path == "/report":
                body = b'<p id="status">Selected report</p><video src="/clip.mp4"></video>'
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/canvas":
                body = (Path(__file__).parent / "fixtures/canvas.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path in {"/login", "/home"}:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                if self.path == "/login":
                    body = b'''<input data-test="login-username"><input data-test="login-password">
                    <button data-test="login-submit" onclick="document.cookie='session=fixture;path=/';location.href='/home'">Sign in</button>'''
                else:
                    body = b'<main data-testid="nav-profile">Authenticated</main>'
                self.wfile.write(body)
                return
            if self.path == "/chain":
                self.send_response(302)
                self.send_header("Location", "/jump")
                self.end_headers()
                return
            if self.path == "/jump":
                self.send_response(302)
                self.send_header("Location", "/api/eval/state")
                self.end_headers()
                return
            if self.path.startswith("/api/eval") or self.path == "/reset":
                state["private_hits"] += 1
            if self.path == "/save":
                state["saved"] = True
            self.send_response(200)
            if self.path == "/download":
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Disposition", 'attachment; filename="report.csv"')
                body = b"name,value\nexample,42\n"
            else:
                self.send_header("Content-Type", "text/html")
                body = b"""<html><title>Fixture</title><body>
                <label>Name <input aria-label="Name"></label>
                <button onclick="fetch('/save').then(()=>document.querySelector('#status').textContent='Saved')">Save</button>
                <p id="status">Ready</p><a href="/download">Download report</a>
                <a href="/jump">Redirect to private endpoint</a>
                <a target="_blank" href="/chain">Redirect popup</a>
                <a target="_blank" href="/api/eval/state">Private popup</a>
                </body></html>"""
                if "session=fixture" in self.headers.get("Cookie", ""):
                    body += b'<main data-testid="nav-profile">Authenticated</main>'
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", state
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def website():
    with site_server() as site:
        yield site


@pytest.fixture
def website_pair():
    with site_server() as first, site_server() as second:
        yield first, second


@pytest.fixture
def task():
    from webarena_pro_core.task import WebArenaProTaskConfig

    evaluation = {"nodes": [{"id": "answer", "type": "answer_match", "eval_config": {"exact_match": "42"}}]}
    return WebArenaProTaskConfig(
        task_id="fixture",
        intent="Report the answer 42",
        sites=("jobportal",),
        container_name="fixture",
        start_url="http://fixture.invalid",
        evaluation=evaluation,
        raw_task={"task_id": "fixture", "intent": "Report the answer 42", "sites": ["jobportal"], "eval": evaluation},
    )


@pytest.fixture
def control_path():
    # Pytest's per-test paths can exceed the AF_UNIX path limit on macOS.
    with tempfile.TemporaryDirectory(prefix="wp-mcp-") as directory:
        yield Path(directory) / "control.sock"



@pytest.fixture
def media_website(tmp_path):
    from webarena_pro_media.binaries import ffmpeg_binary

    video = tmp_path / "fixture.mp4"
    subprocess.run(
        [
            ffmpeg_binary(),
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=64x48:r=10:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(video),
        ],
        check=True,
        timeout=30,
    )
    state = {"saved": False, "private_hits": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path == "/save":
                state["saved"] = True
            if self.path.startswith("/api/eval"):
                state["private_hits"] += 1
            body = b"<html><title>Fixture</title><button onclick=\"fetch('/save').then(()=>document.querySelector('p').textContent='Saved')\">Save</button><p>Ready</p><a href=\"/api/eval/state\">Private</a></html>"
            body += (
                b'<video controls preload="none" src="/fixture.mp4" aria-label="Test clip"></video>'
            )
            if self.path == "/fixture.mp4":
                body = video.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type", "video/mp4" if self.path == "/fixture.mp4" else "text/html"
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", state
    server.shutdown()
    server.server_close()
    thread.join()
