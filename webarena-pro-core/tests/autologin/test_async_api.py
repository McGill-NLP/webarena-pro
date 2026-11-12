import asyncio
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread, get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import async_playwright

from webarena_pro_core.autologin import async_api, sync_api
from webarena_pro_core.website_metadata import WEBSITE_LOGIN_PATHS


class Locator:
    def __init__(self, page):
        self.page = page

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def or_(self, other):
        return self

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.page.record(name, args, kwargs)
        return call


class AsyncLocator(Locator):
    async def count(self):
        return 1

    def __getattr__(self, name):
        return AsyncMock(side_effect=super().__getattr__(name))


class ResponseEvent:
    value = SimpleNamespace(ok=True, status=200)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class AsyncResponseEvent:
    @property
    async def value(self):
        return ResponseEvent.value

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


class Page:
    def __init__(self):
        self.url = "about:blank"
        self.calls = []

    def record(self, name, args, kwargs):
        self.calls.append((name, tuple("predicate" if callable(a) else a for a in args), kwargs))

    def goto(self, url, **kwargs):
        self.url = url
        self.record("goto", (url,), kwargs)

    def evaluate(self, script, *args):
        self.record("evaluate", (script, *args), {})
        return True

    def expect_response(self, *args, **kwargs):
        return ResponseEvent()

    def __getattr__(self, name):
        if name == "locator" or name.startswith("get_by_"):
            def locator(*args, **kwargs):
                self.record(name, args, kwargs)
                return Locator(self)
            return locator
        def call(*args, **kwargs):
            self.record(name, args, kwargs)
        return call


class AsyncPage(Page):
    async def goto(self, *args, **kwargs):
        return super().goto(*args, **kwargs)

    async def evaluate(self, *args, **kwargs):
        return super().evaluate(*args, **kwargs)

    def expect_response(self, *args, **kwargs):
        return AsyncResponseEvent()

    def __getattr__(self, name):
        if name == "locator" or name.startswith("get_by_"):
            def locator(*args, **kwargs):
                self.record(name, args, kwargs)
                return AsyncLocator(self)
            return locator
        return AsyncMock(side_effect=super().__getattr__(name))


@pytest.mark.parametrize("site", WEBSITE_LOGIN_PATHS)
async def test_all_site_flows_issue_equivalent_browser_operations(site):
    sync_page, async_page = Page(), AsyncPage()
    urls = {site: "http://fixture"}
    sync_api.AutoLogin(urls=urls).perform_login(site, sync_page)
    await async_api.AutoLogin(urls=urls).perform_login(site, async_page)
    assert async_page.calls == sync_page.calls


def test_generated_async_flows_are_current():
    subprocess.run([sys.executable, str(Path(__file__).parents[2] / "scripts/generate_autologin_async.py"), "--check"], check=True)


async def test_retry_and_cancellation_close_temporary_pages(monkeypatch):
    pages = [SimpleNamespace(close=AsyncMock(), context=object()) for _ in range(3)]
    context = SimpleNamespace(new_page=AsyncMock(side_effect=pages))
    login = async_api.AutoLogin()
    login.perform_login = AsyncMock(side_effect=[RuntimeError("warming up"), None])
    login.verify_login = AsyncMock(return_value=True)
    monkeypatch.setattr(async_api, "LOGIN_RETRY_DELAY_SECONDS", 0)
    await login.ui_login("x-lite", SimpleNamespace(context=context))
    assert login.perform_login.await_count == 2
    for page in pages[:2]:
        page.close.assert_awaited_once()
    login.perform_login.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await login.ui_login("x-lite", SimpleNamespace(context=context))
    pages[2].close.assert_awaited_once()


async def test_readiness_supports_async_and_offloads_sync_callbacks():
    from webarena_pro_core.autologin._shared import run_ready_callback
    main_thread = get_ident()
    seen = []
    await run_ready_callback(lambda site: seen.append((site, get_ident())), "x-lite")
    assert seen[0][0] == "x-lite" and seen[0][1] != main_thread
    ready = AsyncMock()
    await run_ready_callback(ready, "notion")
    ready.assert_awaited_once_with("notion")


@pytest.fixture
def website():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path == "/login":
                body = b'''<input data-test="login-username"><input data-test="login-password">
<button data-test="login-submit" onclick="document.cookie='session=fixture;path=/';location.href='/home'">Sign in</button>'''
            elif self.path == "/notion/login":
                body = b'''<input type="email"><input type="password">
<button onclick="fetch('/api/login',{method:'POST'}).then(()=>location.href='/app')">Enter workspace</button>'''
            else:
                body = b'<main data-testid="nav-profile">Authenticated</main>' if "session=fixture" in self.headers.get("Cookie", "") else b'<input data-test="login-username">'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.send_response(200)
            self.send_header("Set-Cookie", "session=fixture; Path=/")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{}')

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_sync_storage_state_with_real_browser(website, tmp_path):
    path = sync_api.save_storage_state("x-lite", tmp_path / "sync.json", urls={"x-lite": website}, login_urls={"x-lite": website + "/login"}, max_attempts=1)
    import json
    assert json.loads(path.read_text())["cookies"][0]["name"] == "session"


async def test_async_storage_state_with_real_browser(website, tmp_path):
    path = await async_api.save_storage_state("x-lite", tmp_path / "async.json", urls={"x-lite": website}, login_urls={"x-lite": website + "/login"}, max_attempts=1)
    import json
    assert json.loads(path.read_text())["cookies"][0]["value"] == "fixture"


async def test_notion_async_response_context_manager(website):
    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch()
        try:
            page = await browser.new_page()
            # Route the normal /login URL to the local Notion form.
            await page.route(website + "/login", lambda route: route.fulfill(status=200, content_type="text/html", body='''<input type="email"><input type="password"><button onclick="fetch('/api/login',{method:'POST'}).then(()=>location.href='/app')">Enter workspace</button>'''))
            await async_api.AutoLogin(urls={"notion": website}).perform_login("notion", page)
            assert page.url == website + "/app"
        finally:
            await browser.close()


@pytest.mark.parametrize("site", WEBSITE_LOGIN_PATHS)
async def test_all_site_verification_probes_and_cleanup_match(site):
    sync_pages, async_pages = [], []
    def new_sync_page():
        page = Page()
        sync_pages.append(page)
        return page
    async def new_async_page():
        page = AsyncPage()
        async_pages.append(page)
        return page
    config = dict(urls={site: "http://fixture"}, login_urls={site: "http://fixture/login"})
    expected = sync_api.AutoLogin(**config).verify_login(site, SimpleNamespace(new_page=new_sync_page))
    actual = await async_api.AutoLogin(**config).verify_login(site, SimpleNamespace(new_page=new_async_page))
    assert actual == expected
    assert [page.calls for page in async_pages] == [page.calls for page in sync_pages]
