import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace

import pytest
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright

from webarena_pro_core.autologin import async_api, sync_api


@pytest.fixture
def peppermint_website(request):
    response_delay, token_delay_ms = getattr(request, "param", (0, 0))
    site = SimpleNamespace(login_status=200, login_requests=0, profile_headers=[])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, body, *, status=200, content_type="text/html"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(body.encode())

        def do_GET(self):
            if self.path == "/auth/login":
                self.respond('''
<label>Email address<input id="email"></label>
<label>Password<input type="password" id="password"></label>
<button onclick="login()">Sign In</button>
<script>
async function login() {
    const response = await fetch('/api/v1/auth/login', {method: 'POST'});
    if (!response.ok) return;
    const data = await response.json();
    await new Promise(resolve => setTimeout(resolve, TOKEN_DELAY));
    localStorage.setItem('token', data.token);
    location.href = '/';
}
</script>'''.replace("TOKEN_DELAY", str(token_delay_ms)))
            elif self.path == "/api/v1/auth/profile":
                authorization = self.headers.get("Authorization")
                site.profile_headers.append(authorization)
                self.respond(
                    "{}",
                    status=200 if authorization == "Bearer fixture" else 401,
                    content_type="application/json",
                )
            else:
                self.respond('''<main></main><script>
fetch('/api/v1/auth/profile', {
    headers: {Authorization: 'Bearer ' + (localStorage.getItem('token') || undefined)}
}).then(response => {
    document.querySelector('main').textContent = response.ok ? 'Dashboard' : 'Sign In';
});
</script>''')

        def do_POST(self):
            assert self.path == "/api/v1/auth/login"
            site.login_requests += 1
            time.sleep(response_delay)
            try:
                self.respond(
                    json.dumps({"token": "fixture"}),
                    status=site.login_status,
                    content_type="application/json",
                )
            except (BrokenPipeError, ConnectionResetError):
                # A failing login may close its temporary page before the response.
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    site.url = f"http://127.0.0.1:{server.server_port}"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield site
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def assert_authenticated(site, storage_state):
    assert site.login_requests == 1
    assert site.profile_headers
    assert set(site.profile_headers) == {"Bearer fixture"}
    assert storage_state["origins"][0]["localStorage"] == [
        {"name": "token", "value": "fixture"}
    ]


@pytest.mark.parametrize(
    "peppermint_website", [(0.5, 0), (0, 500)],
    indirect=True, ids=["slow-response", "slow-token-storage"],
)
def test_sync_peppermint_login_waits_for_authentication(peppermint_website):
    site = peppermint_website
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        try:
            context = browser.new_context()
            page = context.new_page()
            login = sync_api.AutoLogin(urls={"peppermint": site.url})
            login.ui_login("peppermint", page, max_attempts=1)
            assert_authenticated(site, page.context.storage_state())
            assert page.context.pages == [page]
        finally:
            browser.close()


@pytest.mark.parametrize(
    "peppermint_website", [(0.5, 0), (0, 500)],
    indirect=True, ids=["slow-response", "slow-token-storage"],
)
async def test_async_peppermint_login_waits_for_authentication(peppermint_website):
    site = peppermint_website
    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch()
        try:
            context = await browser.new_context()
            page = await context.new_page()
            login = async_api.AutoLogin(urls={"peppermint": site.url})
            await login.ui_login("peppermint", page, max_attempts=1)
            assert_authenticated(site, await page.context.storage_state())
            assert page.context.pages == [page]
        finally:
            await browser.close()


@pytest.mark.parametrize("status", [401, 500])
def test_sync_peppermint_login_reports_http_failure(peppermint_website, status):
    site = peppermint_website
    site.login_status = status
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        try:
            context = browser.new_context()
            page = context.new_page()
            login = sync_api.AutoLogin(urls={"peppermint": site.url})
            with pytest.raises(RuntimeError, match="after 1 attempts") as error:
                login.ui_login("peppermint", page, max_attempts=1)
            assert str(error.value.__cause__) == f"Peppermint login failed with HTTP {status}"
            assert site.login_requests == 1
            assert site.profile_headers == []
            assert page.context.pages == [page]
        finally:
            browser.close()


@pytest.mark.parametrize("status", [401, 500])
async def test_async_peppermint_login_reports_http_failure(peppermint_website, status):
    site = peppermint_website
    site.login_status = status
    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch()
        try:
            context = await browser.new_context()
            page = await context.new_page()
            login = async_api.AutoLogin(urls={"peppermint": site.url})
            with pytest.raises(RuntimeError, match="after 1 attempts") as error:
                await login.ui_login("peppermint", page, max_attempts=1)
            assert str(error.value.__cause__) == f"Peppermint login failed with HTTP {status}"
            assert site.login_requests == 1
            assert site.profile_headers == []
            assert page.context.pages == [page]
        finally:
            await browser.close()
