import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from webarena_pro_core.task import WebArenaProTaskConfig


@pytest.fixture
def task():
    raw = {
        "task_id": "fixture",
        "intent": "Save the form and report 42",
        "sites": ["jobportal"],
        "eval": {
            "nodes": [
                {"id": "answer", "type": "answer_match", "eval_config": {"exact_match": "42"}}
            ]
        },
    }
    return WebArenaProTaskConfig.from_raw_task(raw, container_name="fixture")


@pytest.fixture
def control_path():
    # Pytest's per-test paths can exceed the AF_UNIX path limit on macOS.
    with tempfile.TemporaryDirectory(prefix="wp-harbor-") as directory:
        yield Path(directory) / "control.sock"


@pytest.fixture
def website(tmp_path):
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
