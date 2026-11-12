"""Controlled Save-to-document regression; this is not an ERPNext task replay."""

import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

import pytest

from webarena_pro_mcp.mcp_client import text_content
from webarena_pro_mcp.media_policy import MediaSettings
from webarena_pro_mcp.session import open_session

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(os.environ.get("WP_MCP_BROWSER_TESTS") != "1",
                       reason="Set WP_MCP_BROWSER_TESTS=1 after webarena-pro-mcp install"),
]


async def test_save_percent_named_document_keeps_media_inventory_and_terminal_grade(tmp_path, task):
    # Test 049 requires this exact name. The original failed post-Save URL was
    # not captured; exercise the app's route shape without claiming a live replay.
    name = "Achieve CPU yields of 80% per wafer"
    path = "/app/quality-goal/" + quote(name, safe="")
    requested = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            requested.append(self.path)
            body = (
                '<html><title>Quality Goal fixture</title>'
                '<button onclick="saveGoal()">Save</button><p id="status">Ready</p>'
                '<script>function saveGoal() {'
                f'history.pushState({{}}, "", {json.dumps(path)});'
                'document.querySelector("#status").textContent="Saved";'
                '}</script></html>'
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    config = {
        "task": task.raw_task, "urls": {"jobportal": url}, "max_steps": 5,
        "media": MediaSettings(transcription="disabled").as_dict(),
    }
    try:
        async with open_session(config, tmp_path / "evidence", fixture_urls=config["urls"]) as session:
            initial = await session.call("browser_snapshot", {})
            ref = re.search(r'button "Save" \[ref=([^\]]+)\]', text_content(initial)).group(1)
            saved = await session.call("browser_click", {"target": ref})
            assert not saved["isError"], saved
            assert "Saved" in text_content(saved)
            assert path in text_content(saved)
            assert session.trajectory[-1]["obs"]["url"] == url + path
            # Also verify that the browser's request guard accepts a reload of
            # the encoded document, not just a same-document history mutation.
            reloaded = await session.call("browser_navigate", {"url": url + path})
            assert not reloaded["isError"], reloaded
            assert path in requested
            rejected = await session.call("browser_navigate", {"url": url + "/%2572eset"})
            assert rejected["isError"]
            assert not any("reset" in request or "%2572eset" in request for request in requested)
            assert not (await session.call("webarena_submit", {"answer": "42"}))["isError"]
            result = await session.finalize()
            assert result["status"] == "graded" and result["score"] == 1
            assert result["steps"] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
