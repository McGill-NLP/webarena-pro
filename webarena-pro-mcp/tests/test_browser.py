import os
import re
import json
import sys
from pathlib import Path

import pytest
from webarena_pro_mcp.mcp_client import connect, text_content
from webarena_pro_mcp.media_policy import MediaSettings
from webarena_pro_mcp.evaluation import grade
from webarena_pro_mcp.supervisor import Supervisor
from webarena_pro_mcp.tool_policy import PolicyError, ToolPolicy

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("WP_MCP_BROWSER_TESTS") != "1",
        reason="Set WP_MCP_BROWSER_TESTS=1 after webarena-pro-mcp install",
    ),
]


def reference(text, label):
    for line in text.splitlines():
        if label in line and (match := re.search(r"\[ref=([\w-]+)\]", line)):
            return match[1]
    raise AssertionError(f"No reference for {label}: {text}")


async def test_canvas_coordinate_actions_and_editing_shortcuts(tmp_path, website, task):
    url, _ = website
    supervisor = Supervisor(task, tmp_path, "fixture", fixture_urls={"jobportal": url})
    try:
        setup = await supervisor.start(30)
        policy = ToolPolicy([url], blocked_paths=setup["blocked_paths"])
        async with connect(setup["endpoint"], tmp_path / "browser", policy, 30) as browser:
            initial = await browser.call("browser_navigate", {"url": url + "/canvas"})
            assert not initial["isError"], initial
            screenshot = await browser.call("browser_take_screenshot", {"scale": "css"})
            assert any(part["type"] == "image" for part in screenshot["content"])
            for name, args in [
                ("browser_mouse_click_xy", {"x": 60, "y": 60}),
                ("browser_mouse_drag_xy", {"startX": 60, "startY": 60, "endX": 160, "endY": 160}),
                ("browser_mouse_move_xy", {"x": 320, "y": 80}),
                ("browser_mouse_down", {"button": "left"}),
                ("browser_mouse_move_xy", {"x": 360, "y": 100}),
                ("browser_mouse_up", {"button": "left"}),
                ("browser_mouse_move_xy", {"x": 40, "y": 300}),
                ("browser_mouse_down", {}),
                ("browser_mouse_move_xy", {"x": 60, "y": 320}),
                ("browser_mouse_move_xy", {"x": 100, "y": 300}),
                ("browser_mouse_up", {}),
                ("browser_press_key", {"key": "Control+g"}),
                ("browser_press_key", {"key": "Meta+g"}),
            ]:
                result = await browser.call(name, args)
                assert not result["isError"], (name, result)
            snapshot = text_content(result)
            match = re.search(r'paragraph \[ref=[\w-]+\]: (".*")', snapshot)
            assert match, snapshot
            state = json.loads(json.loads(match[1]))
            assert state == {"clicks": 4, "shapeX": 140, "shapeY": 140,
                             "handleX": 360, "handleY": 100, "points": 3, "groups": 2}
            modifier = "Meta" if sys.platform == "darwin" else "Control"
            # Penpot uses the asynchronous Clipboard API, which needs explicit
            # permissions even when ordinary input copy/paste already works.
            await browser.call("browser_press_key", {"key": modifier + "+c"})
            copied = await browser.call("browser_wait_for", {"text": "Canvas copied through Clipboard API"})
            assert not copied["isError"], copied
            await browser.call("browser_press_key", {"key": modifier + "+v"})
            pasted = await browser.call("browser_wait_for", {"text": "Canvas pasted: copied canvas shape"})
            assert not pasted["isError"], pasted
            # Ordinary input copy/paste remains available as well.
            snapshot = text_content(await browser.call("browser_snapshot", {}))
            await browser.call("browser_click", {"target": reference(snapshot, 'textbox "Copy source"')})
            await browser.call("browser_press_key", {"key": modifier + "+a"})
            await browser.call("browser_press_key", {"key": modifier + "+c"})
            snapshot = text_content(await browser.call("browser_snapshot", {}))
            await browser.call("browser_click", {"target": reference(snapshot, 'textbox "Paste destination"')})
            pasted = await browser.call("browser_press_key", {"key": modifier + "+v"})
            destination = next(
                line for line in text_content(pasted).splitlines() if 'textbox "Paste destination"' in line
            )
            assert destination.endswith(": canvas clipboard text"), destination
            with pytest.raises(PolicyError):
                await browser.call("browser_press_key", {"key": "Control+Shift+J"})
            with pytest.raises(PolicyError):
                await browser.call("browser_evaluate", {"function": "() => document.cookie"})
    finally:
        await supervisor.close()


async def test_clipboard_api_on_non_loopback_http_task_origin(tmp_path, task):
    from playwright.async_api import async_playwright

    url = "http://penpot.fixture"
    supervisor = Supervisor(task, tmp_path, "fixture", fixture_urls={"jobportal": url})
    try:
        setup = await supervisor.start(30)
        async with async_playwright() as runtime:
            observer = await runtime.chromium.connect_over_cdp(setup["endpoint"])
            context = observer.contexts[0]
            # Serve a controlled fixture at a non-loopback HTTP origin without
            # relying on external DNS. All tested actions still use MCP.
            await context.route(url + "/canvas", lambda route: route.fulfill(
                content_type="text/html",
                body=(Path(__file__).parent / "fixtures/canvas.html").read_text(),
            ))
            policy = ToolPolicy([url], blocked_paths=setup["blocked_paths"])
            async with connect(setup["endpoint"], tmp_path / "browser", policy, 30) as browser:
                initial = await browser.call("browser_navigate", {"url": url + "/canvas"})
                assert not initial["isError"], initial
                page = next(page for page in context.pages if page.url == url + "/canvas")
                assert await page.evaluate("window.isSecureContext")
                await browser.call("browser_mouse_click_xy", {"x": 60, "y": 60})
                modifier = "Meta" if sys.platform == "darwin" else "Control"
                await browser.call("browser_press_key", {"key": modifier + "+c"})
                copied = await browser.call("browser_wait_for", {"text": "Canvas copied through Clipboard API"})
                assert not copied["isError"], copied
                await browser.call("browser_press_key", {"key": modifier + "+v"})
                pasted = await browser.call("browser_wait_for", {"text": "Canvas pasted: copied canvas shape"})
                assert not pasted["isError"], pasted
                with pytest.raises(PolicyError):
                    await browser.call("browser_navigate", {"url": "http://unconfigured.fixture"})
    finally:
        await supervisor.close()


async def test_real_mcp_ui_grade_download_and_guards(tmp_path, website, task):
    url, state = website
    task.evaluation = {
        "nodes": [
            {"id": "answer", "type": "answer_match", "eval_config": {"exact_match": "42"}},
            {"id": "download", "type": "file_downloaded", "eval_config": {"extension": ".csv"}},
            {"id": "dom", "type": "ui_state", "eval_config": {"checks": [
                {"method": "text_contains", "selector": "#status", "text": "Saved"},
            ]}},
        ]
    }
    task.raw_task["eval"] = task.evaluation
    supervisor = Supervisor(task, tmp_path, "fixture", fixture_urls={"jobportal": url})
    try:
        setup = await supervisor.start(30)
        policy = ToolPolicy([url], blocked_paths=setup["blocked_paths"])
        async with connect(setup["endpoint"], tmp_path / "browser", policy, 30) as browser:
            initial = await browser.call("browser_navigate", {"url": url})
            assert not initial["isError"], initial
            text = text_content(initial)
            # The pinned server uses `target`; tests fail if its API changes.
            filled = await browser.call(
                "browser_type", {"target": reference(text, "textbox"), "text": "Alice"}
            )
            assert not filled["isError"], filled
            clicked = await browser.call(
                "browser_click", {"target": reference(text_content(filled), 'button "Save"')}
            )
            assert not clicked["isError"], clicked
            await browser.call("browser_wait_for", {"text": "Saved"})
            snapshot = await browser.call("browser_snapshot", {})
            assert state["saved"]
            screenshot = await browser.call("browser_take_screenshot", {"scale": "css"})
            assert any(part["type"] == "image" for part in screenshot["content"])
            downloaded = await browser.call(
                "browser_click", {"target": reference(text_content(snapshot), "Download report")}
            )
            assert not downloaded["isError"], downloaded
            result, _ = await grade(browser, supervisor, [], "send_msg_to_user('42')", 30)
            assert result["score"] == 1.0, result
            evidence = result["ui_evidence"]
            assert evidence["status"] == "ok" and evidence["step"] == 0
            assert evidence["tab_id"] == "0" and evidence["url"].rstrip("/") == url
            assert next(iter(evidence["results"].values()))["text"] == "Saved"
            with pytest.raises(PolicyError):
                await browser.call("browser_evaluate", {"function": "() => fetch('/reset')"})
            with pytest.raises(PolicyError):
                await browser.call("browser_navigate", {"url": url + "/reset"})
            # Redirect enforcement is in the browser, beyond tool validation.
            await browser.call("browser_navigate", {"url": url + "/jump"})
            assert state["private_hits"] == 0
            await browser.call("browser_navigate", {"url": url + "/chain"})
            assert state["private_hits"] == 0
            restored = await browser.call("browser_navigate", {"url": url})
            await browser.call(
                "browser_click", {"target": reference(text_content(restored), "Redirect popup")}
            )
            assert state["private_hits"] == 0
            diagnostics = await supervisor.call("diagnostics")
            assert diagnostics["blocked_requests"]
            assert diagnostics["downloads"][0]["suggested_filename"] == "report.csv"
    finally:
        await supervisor.close()


async def test_async_autologin_with_guards_and_temporary_pages(tmp_path, website, task):
    url, _ = website
    task.require_login = True
    task.sites = ("x-lite",)
    supervisor = Supervisor(task, tmp_path, "fixture", fixture_urls={"x-lite": url})
    try:
        setup = await supervisor.start(30)
        policy = ToolPolicy([url], blocked_paths=setup["blocked_paths"])
        async with connect(setup["endpoint"], tmp_path / "browser", policy, 30) as browser:
            result = await browser.call("browser_navigate", {"url": url})
            assert "Authenticated" in text_content(result)
            # The login and verification tabs are closed before solving.
            tabs = await browser.call("browser_tabs", {"action": "list"})
            assert len(re.findall(r"^- \d+:", text_content(tabs), re.MULTILINE)) == 1
            assert not (await supervisor.call("diagnostics"))["blocked_requests"]
    finally:
        await supervisor.close()


async def test_media_connection_preserves_download_evidence(tmp_path, website, task):
    url, _ = website
    task.evaluation = {"nodes": [
        {"id": "download", "type": "file_downloaded", "eval_config": {
            "extension": ".csv", "magic_bytes": "name,value\nexample,42\n",
        }},
    ]}
    task.raw_task["eval"] = task.evaluation
    supervisor = Supervisor(task, tmp_path, "fixture", fixture_urls={"jobportal": url})
    try:
        setup = await supervisor.start(30)
        policy = ToolPolicy([url], blocked_paths=setup["blocked_paths"], media=MediaSettings())
        async with connect(setup["endpoint"], tmp_path / "browser", policy, 30) as browser:
            page = await browser.call("browser_navigate", {"url": url})
            await browser.call("browser_click", {
                "target": reference(text_content(page), "Download report"),
            })
            result, _ = await grade(browser, supervisor, [], "send_msg_to_user('42')", 30)
            assert result["score"] == 1, result
    finally:
        await supervisor.close()


async def test_multiple_task_origins_and_selected_tab_evaluation(tmp_path, website, task):
    url, _ = website
    other = url.replace("127.0.0.1", "localhost")
    task.sites = ("jobportal", "mattermost")
    task.evaluation["nodes"].append({"id": "ui", "type": "ui_state", "eval_config": {
        "checks": [{"method": "text_contains", "selector": "#status", "text": "Ready"}],
    }})
    supervisor = Supervisor(task, tmp_path, "fixture", fixture_urls={"jobportal": url, "mattermost": other})
    try:
        setup = await supervisor.start(30)
        policy = ToolPolicy([url, other], blocked_paths=setup["blocked_paths"])
        async with connect(setup["endpoint"], tmp_path / "browser", policy, 30) as browser:
            initial = await browser.call("browser_navigate", {"url": url})
            saved = await browser.call("browser_click", {
                "target": reference(text_content(initial), 'button "Save"'),
            })
            assert not saved["isError"], saved
            saved_status = await browser.call("browser_wait_for", {"text": "Saved"})
            assert not saved_status["isError"], saved_status
            first_tab = await browser.identity()
            opened = await browser.call("browser_tabs", {"action": "new", "url": other})
            assert not opened["isError"], opened
            assert (await browser.identity())["target_id"] != first_tab["target_id"]
            result, snapshot = await grade(browser, supervisor, [], "send_msg_to_user('42')", 30)
            assert result["score"] == 1
            assert other in text_content(snapshot)
            # The fresh grading observer has its own page enumeration order.
            # Verify the selected document and distinct UI state, not its index.
            assert result["ui_evidence"]["url"].rstrip("/") == other
            assert any(probe["text"] == "Ready" for probe in result["ui_evidence"]["results"].values())
            await browser.call("browser_tabs", {"action": "select", "index": 0})
            assert await browser.identity() == first_tab
            result, snapshot = await grade(browser, supervisor, [], "send_msg_to_user('42')", 30)
            assert result["score"] == 0  # Binary AND: this tab is Saved instead of Ready.
            assert result["dag_results"]["answer"]["passed"]
            assert not result["dag_results"]["ui"]["passed"]
            assert url in text_content(snapshot)
            assert result["ui_evidence"]["url"].rstrip("/") == url
            assert any(probe["text"] == "Saved" for probe in result["ui_evidence"]["results"].values())
    finally:
        await supervisor.close()


async def test_external_clients_have_isolated_sessions_and_cleanup(tmp_path, website_pair, task):
    import asyncio
    import json

    from webarena_pro_mcp.artifacts import safe_error
    from webarena_pro_mcp.session import open_session

    ready = asyncio.Barrier(2)
    first_closed = asyncio.Event()
    supervisors = []

    async def client(index):
        url, state = website_pair[index]
        config = {"task": task.raw_task, "urls": {"jobportal": url}, "media": {"enabled": False}}
        try:
            async with open_session(config, tmp_path / str(index), fixture_urls=config["urls"]) as session:
                supervisors.append(session.supervisor)
                await asyncio.wait_for(ready.wait(), 30)
                if index == 0:
                    raise RuntimeError("external client exited")
                await asyncio.wait_for(first_closed.wait(), 30)
                snapshot = await session.call("browser_snapshot", {})
                await session.call("browser_click", {"target": reference(text_content(snapshot), 'button "Save"')})
                await session.call("browser_wait_for", {"text": "Saved"})
                assert state["saved"] and not website_pair[0][1]["saved"]
                await session.call("webarena_submit", {"answer": "42"})
                assert (await session.finalize())["score"] == 1
        except Exception as exc:
            # The MCP transport can wrap the caller's error in nested task groups.
            assert index == 0 and safe_error(exc) == "RuntimeError: external client exited"
        finally:
            if index == 0:
                first_closed.set()

    await asyncio.wait_for(asyncio.gather(client(0), client(1)), 90)
    assert all(not supervisor.process.is_alive() for supervisor in supervisors)
    assert not (tmp_path / "0/result.json").exists()
    assert json.loads((tmp_path / "1/result.json").read_text())["status"] == "graded"


async def test_stable_target_identity_across_duplicate_tabs_redirect_and_close(tmp_path, website, task):
    from playwright.async_api import async_playwright
    from webarena_pro_mcp.browser_identity import BrowserIdentityError, page_identity
    from webarena_pro_mcp.media_server import MediaEngine
    from types import SimpleNamespace

    url, _ = website
    task.evaluation["nodes"].append({"id": "ui", "type": "ui_state", "eval_config": {
        "checks": [{"method": "text_contains", "selector": "#status", "text": "Selected report"}],
    }})
    supervisor = Supervisor(task, tmp_path, "fixture", fixture_urls={"jobportal": url})
    try:
        setup = await supervisor.start(30)
        policy = ToolPolicy([url], blocked_paths=setup["blocked_paths"], media=MediaSettings())
        async with connect(setup["endpoint"], tmp_path / "browser", policy, 30) as browser:
            async with async_playwright() as runtime:
                observer = await runtime.chromium.connect_over_cdp(setup["endpoint"], no_defaults=True)
                context = observer.contexts[0]
                await browser.call("browser_navigate", {"url": url})
                await browser.call("browser_tabs", {"action": "new", "url": url})
                await browser.call("browser_tabs", {"action": "select", "index": 1})
                selected = await browser.identity()
                # Duplicate URLs must resolve by target even when another CDP
                # client's page list has the opposite order.
                identities = [(page, await page_identity(page)) for page in context.pages]
                selected_page = next(page for page, identity in identities if identity == selected)
                engine = MediaEngine({"settings": MediaSettings().as_dict(), "urls": [url],
                                      "blocked_paths": [], "directory": str(tmp_path / "direct-media"),
                                      "endpoint": setup["endpoint"]})
                engine.context = SimpleNamespace(pages=list(reversed(context.pages)))
                assert await engine.discover(selected) == []
                await browser.call("browser_navigate", {"url": url + "/report-redirect"})
                assert (await browser.inventory())[0]["kind"] == "video"
                result, _ = await grade(browser, supervisor, [], "send_msg_to_user('42')", 30)
                assert result["score"] == 1, result
                # Same-URL reload invalidates an already captured document.
                previous = await browser.identity()
                await selected_page.reload()
                with pytest.raises(BrowserIdentityError, match="document changed"):
                    await supervisor.call("evaluate", identity=previous, snapshot="stale", trajectory=[], last_action="submit")
                await browser.call("browser_tabs", {"action": "close", "index": 0})
                result, _ = await grade(browser, supervisor, [], "send_msg_to_user('42')", 30)
                assert result["score"] == 1, result
                closed = await browser.identity()
                await browser.call("browser_tabs", {"action": "new", "url": url})
                await browser.call("browser_tabs", {"action": "close", "index": 0})
                with pytest.raises(BrowserIdentityError, match="no longer available"):
                    await supervisor.call("evaluate", identity=closed, snapshot="stale", trajectory=[], last_action="submit")
    finally:
        await supervisor.close()


async def test_media_inventory_recovers_download_non_html_404_and_blocked_navigation(tmp_path, website, task):
    from webarena_pro_mcp.session import open_session

    url, state = website
    config = {"task": task.raw_task, "urls": {"jobportal": url}, "media": MediaSettings().as_dict()}
    async with open_session(config, tmp_path / "episode", fixture_urls=config["urls"]) as session:
        for path in ("/plain.txt", "/missing-page", "/"):
            result = await session.call("browser_navigate", {"url": url + path})
            assert not result["isError"], result
            assert session.failure is None
        downloaded = await session.call("browser_click", {
            "target": reference(text_content(result), "Download report"),
        })
        assert not downloaded["isError"], downloaded
        assert session.failure is None
        # A download into a new tab may leave an empty browser document.
        await session.call("browser_tabs", {"action": "new"})
        download_navigation = await session.call("browser_navigate", {"url": url + "/download"})
        assert session.failure is None, download_navigation
        await session.call("browser_tabs", {"action": "close"})
        for blocked in (url + "/api/eval/state", "http://unconfigured.fixture/", "chrome-error://chromewebdata/"):
            rejected = await session.call("browser_navigate", {"url": blocked})
            assert rejected["isError"] and session.failure is None, rejected
        # JSON remains blocked by the existing response policy, even on an
        # otherwise permitted task route. Its error document stays recoverable.
        json_navigation = await session.call("browser_navigate", {"url": url + "/data.json"})
        assert json_navigation["isError"] and session.failure is None, json_navigation
        # The guard blocks a private redirect after the action has dispatched.
        failed = await session.call("browser_navigate", {"url": url + "/jump"})
        assert failed["isError"], failed
        assert "browser error page" in text_content(failed), failed
        calls = [json.loads(line) for line in (tmp_path / "episode/calls.jsonl").read_text().splitlines()]
        assert calls[-1]["result"]["media_inventory"]["url_category"] == "browser_error"
        assert session.failure is None and state["private_hits"] == 0
        recovered = await session.call("browser_navigate", {"url": url})
        assert not recovered["isError"] and session.failure is None
        # A consistent browser error document can also be captured for terminal
        # evaluation; answer/download criteria retain their normal semantics.
        await session.call("browser_navigate", {"url": url + "/jump"})
        assert not (await session.call("webarena_submit", {"answer": "42"}))["isError"]
        final = await session.finalize()
        assert final["status"] == "graded" and final["score"] == 1, final
        assert state["private_hits"] == 0
