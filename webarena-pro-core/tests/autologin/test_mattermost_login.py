import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from webarena_pro_core.autologin import async_api, sync_api


@pytest.fixture(params=["link", "aria-link", "aria-button", "direct"])
def mattermost(request):
    controls = {
        "link": '<a href="/login?browser=1">View in Browser</a>',
        "aria-link": '<a href="/login?browser=1" aria-label="View in Browser">Continue</a>',
        "aria-button": '<button aria-label="View in Browser" onclick="location.href=\'/login?browser=1\'">Continue</button>',
    }
    control = controls.get(request.param)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            authenticated = "session=fixture" in self.headers.get("Cookie", "")
            if self.path.startswith("/login") and authenticated:
                self.send_response(302)
                self.send_header("Location", "/team/channels/town-square")
                self.end_headers()
                return
            if self.path == "/login" and control is not None:
                # Match Mattermost: the URL changes before the landing control
                # renders. A count-based fallback commits to the wrong locator.
                body = f"""<script>
history.replaceState(null, '', '/landing');
setTimeout(() => {{ document.body.innerHTML = {json.dumps(control)}; }}, 1000);
</script><body></body>"""
            elif self.path.startswith("/login"):
                body = """<input id="input_loginId"><input id="input_password-input">
<button id="saveSetting" onclick="
if (document.querySelector('#input_loginId').value === 'fixture-user' &&
    document.querySelector('#input_password-input').value === 'fixture-password') {
    document.cookie='session=fixture;path=/';
    location.href='/team/channels/town-square';
}">Sign in</button>"""
            else:
                body = "<main>Town Square</main>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield {
            "urls": {"mattermost": url},
            "login_urls": {"mattermost": f"{url}/login"},
            "credentials": {
                "mattermost": [
                    {"username": "fixture-user", "password": "fixture-password"}
                ]
            },
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_sync_mattermost_login_succeeds_without_retry(mattermost, tmp_path):
    path = sync_api.save_storage_state(
        "mattermost", tmp_path / "sync.json", max_attempts=1, **mattermost
    )
    assert any(
        cookie["name"] == "session" and cookie["value"] == "fixture"
        for cookie in json.loads(path.read_text())["cookies"]
    )


async def test_async_mattermost_login_succeeds_without_retry(mattermost, tmp_path):
    path = await async_api.save_storage_state(
        "mattermost", tmp_path / "async.json", max_attempts=1, **mattermost
    )
    assert any(
        cookie["name"] == "session" and cookie["value"] == "fixture"
        for cookie in json.loads(path.read_text())["cookies"]
    )
