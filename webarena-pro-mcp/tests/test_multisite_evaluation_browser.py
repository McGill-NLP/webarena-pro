"""Task 074's browser topology with local fixtures, not a Nextcloud benchmark run."""

import asyncio
import json
import multiprocessing
import os
import re
import threading
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

from webarena_pro_mcp.mcp_client import text_content
from webarena_pro_mcp.media_policy import MediaSettings
from webarena_pro_mcp.session import open_session
from webarena_pro_mcp.supervisor import Supervisor, _serve_async

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("WP_MCP_BROWSER_TESTS") != "1",
        reason="Set WP_MCP_BROWSER_TESTS=1 after webarena-pro-mcp install",
    ),
]


def _serve_with_unavailable_owner(connection, *args):
    """Model the observed empty owner inventory without killing live Chromium."""
    from playwright.async_api import Browser, BrowserContext, BrowserType
    from playwright._impl._errors import TargetClosedError

    state = {"owner": None, "unavailable": False}
    launch = BrowserType.launch_persistent_context
    pages = BrowserContext.pages.fget
    cdp_session = Browser.new_browser_cdp_session

    async def remember_owner(self, *launch_args, **kwargs):
        context = await launch(self, *launch_args, **kwargs)
        state["owner"] = context
        return context

    def owner_pages(self):
        if state["unavailable"] and self is state["owner"]:
            return []
        return pages(self)

    async def owner_cdp_session(self):
        if state["unavailable"] and self is state["owner"].browser:
            raise TargetClosedError()
        return await cdp_session(self)

    class Connection:
        def __getattr__(self, name):
            return getattr(connection, name)

        def recv(self):
            request = connection.recv()
            if request[0] == "evaluate":
                state["unavailable"] = True
                assert state["owner"].pages == []
                # Record that the deterministic fault really preceded capture.
                (Path(args[1]) / "owner-loss.json").write_text(json.dumps({
                    "owner_pages": len(state["owner"].pages),
                    "requested_identity": request[1]["identity"],
                }))
            return request

    with (
        patch.object(BrowserType, "launch_persistent_context", remember_owner),
        patch.object(BrowserContext, "pages", property(owner_pages)),
        patch.object(Browser, "new_browser_cdp_session", owner_cdp_session),
    ):
        asyncio.run(_serve_async(Connection(), *args))


class UnavailableOwnerSupervisor(Supervisor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.process = multiprocessing.get_context("spawn").Process(
            target=_serve_with_unavailable_owner, args=self.process._args,
        )


@contextmanager
def fixture_site(name):
    state = {"folders": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            body = f"<html><title>{name}</title><h1>{name}</h1>".encode()
            if name == "nextcloud":
                body += b"""
                <label>Folder name <input aria-label="Folder name" id="name"></label>
                <button onclick="fetch('/folders', {method: 'POST', body: document.querySelector('#name').value})
                  .then(response => {if (!response.ok) throw Error('Folder creation failed'); return response.text()})
                  .then(name => {const item = document.createElement('li'); item.dataset.folder = name;
                    item.textContent = name; document.querySelector('#files').append(item);
                    document.querySelector('#status').textContent = 'Folder created';})">Create folder</button>
                <ul id="files"></ul><p id="status">Ready</p>
                """
            body += b"</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            folder = self.rfile.read(int(self.headers["Content-Length"])).decode()
            assert self.path == "/folders" and name == "nextcloud"
            state["folders"].append(folder)
            body = folder.encode()
            self.send_response(201)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def multisite():
    with ExitStack() as stack:
        yield {
            name: stack.enter_context(fixture_site(name))
            for name in ("flight-search", "password-manager", "yt-lite", "notion", "nextcloud")
        }


def reference(result, label):
    for line in text_content(result).splitlines():
        if label in line and (match := re.search(r"\[ref=([\w-]+)\]", line)):
            return match[1]
    raise AssertionError(f"Missing {label}: {text_content(result)}")


async def test_final_grading_after_multisite_folder_creation_and_owner_loss(tmp_path, multisite, monkeypatch):
    """Exercise MCP actions, private capture, and Core; no real sites or model calls."""
    monkeypatch.setattr("webarena_pro_mcp.session.Supervisor", UnavailableOwnerSupervisor)
    urls = {name: site[0] for name, site in multisite.items()}
    config = {
        "task": {
            "task_id": "multisite-folder-fixture",
            "intent": "Create the turkey folder and report 42",
            "sites": list(urls),
            "eval": {"operator": "AND", "nodes": [
                {"id": "answer", "type": "answer_match", "eval_config": {"exact_match": "42"}},
                {"id": "folder", "type": "ui_state", "eval_config": {"checks": [
                    {"method": "element_exists", "selector": "[data-folder='turkey']"},
                ]}},
            ]},
        },
        "urls": urls,
        "media": MediaSettings(transcription="disabled").as_dict(),
        "evaluation_timeout": 30,
    }
    directory = tmp_path / "evidence"
    nextcloud_url = urls["nextcloud"] + "/apps/files/files/10469?dir=/"
    async with open_session(config, directory, fixture_urls=urls) as session:
        async def action(name, arguments):
            result = await session.call(name, arguments)
            assert not result.get("isError"), result
            return result

        await action("browser_tabs", {"action": "new", "url": urls["password-manager"]})
        await action("browser_tabs", {"action": "select", "index": 0})
        for name in ("yt-lite", "notion"):
            await action("browser_tabs", {"action": "new", "url": urls[name]})
        await action("browser_tabs", {"action": "new", "url": nextcloud_url})
        duplicate = await session.browser.identity()
        # A same-URL decoy has no folder. Capture must bind the UI facts
        # to the selected target rather than just its URL or tab position.
        await action("browser_tabs", {"action": "new", "url": nextcloud_url})
        selected = await session.browser.identity()
        assert selected["url"] == duplicate["url"] and selected["target_id"] != duplicate["target_id"]
        snapshot = await action("browser_tabs", {"action": "select", "index": 5})
        snapshot = await action("browser_type", {
            "target": reference(snapshot, 'textbox "Folder name"'), "text": "turkey",
        })
        await action("browser_click", {"target": reference(snapshot, 'button "Create folder"')})
        await action("browser_wait_for", {"text": "Folder created"})
        assert multisite["nextcloud"][1]["folders"] == ["turkey"]
        assert await session.browser.identity() == selected
        steps = session.steps
        assert steps == 10
        await action("webarena_submit", {"answer": "42"})
        trajectory = (directory / "trajectory.jsonl").read_bytes()
        assert session.steps == steps and session.last_action == "send_msg_to_user('42')"

        result = await session.finalize()
        assert result["status"] == "graded", result
        assert result["score"] == result["rewards"]["reward"] == 1
        assert result["steps"] == steps and result["final_answer"] == "42"
        assert (directory / "trajectory.jsonl").read_bytes() == trajectory
        assert json.loads((directory / "owner-loss.json").read_text()) == {
            "owner_pages": 0, "requested_identity": selected,
        }
        capture = json.loads((directory / f"evaluation-{steps}-input.json").read_text())
        assert capture["identity"] == selected and capture["attempt"] == 1
        evaluation = json.loads((directory / f"evaluation-{steps}.json").read_text())
        assert evaluation["dag_results"]["folder"]["passed"]
        assert evaluation["ui_evidence"]["url"] == nextcloud_url
        assert (directory / f"evaluation-{steps}.png").is_file()
        state = json.loads((directory / "evaluation-state.json").read_text())
        assert state["terminal"] and state["status"] == "graded" and state["step"] == steps
        # Disconnecting the evaluator's observer must leave the selected MCP
        # target and the other sites alive, with no extra task mutation.
        assert await session.browser.identity() == selected
        tabs = await session.browser.call("browser_tabs", {"action": "list"})
        assert not tabs.get("isError")
        assert len(re.findall(r"^- \d+:", text_content(tabs), re.MULTILINE)) == 6
        assert multisite["nextcloud"][1]["folders"] == ["turkey"]
