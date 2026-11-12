"""Navigation containment, plus opt-in browser fixtures with no benchmark sites."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from threading import Thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from webarena_pro_bgym.benchmark.navigation import TaskNavigationGuard


def test_internal_error_page_remains_recoverable_and_schemes_stay_restricted():
    guard = TaskNavigationGuard(["http://localhost:8080"])
    assert guard.is_allowed_page("chrome-error://chromewebdata/")
    assert guard.is_allowed_page("about:blank")
    assert guard.is_allowed_page("http://localhost:8080/task")
    for url in ("https://localhost:8080/", "file:///tmp/file", "javascript:alert(1)",
                "http://localhost:8081/", "http://password@localhost:8080/", "chrome://settings/"):
        assert not guard.is_allowed_page(url)


@pytest.mark.parametrize("navigation,allowed", [(True, False), (False, True)])
def test_only_document_navigation_is_blocked(navigation, allowed):
    guard = TaskNavigationGuard(["http://localhost:8080"])
    route = Mock()
    route.request.url = "https://outside.invalid/path?token=secret#private"
    route.request.is_navigation_request.return_value = navigation
    guard._route(route)
    assert route.continue_.called is allowed
    assert route.abort.called is not allowed
    if not allowed:
        assert "outside.invalid/path" in guard.warnings[0]
        assert "secret" not in guard.warnings[0]


@pytest.fixture
def local_site():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(("GET", self.path))
            if self.path == "/failed":
                self.close_connection = True
                return
            port = self.server.server_port
            body = (
                "<html><body><h1>Task fixture</h1>"
                f"<a href='http://localhost:{port}/outside'>External</a>"
                f"<a target='_blank' href='http://localhost:{port}/pricing'>Restore Access</a>"
                "<button>Save</button></body></html>"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            requests.append(("POST", self.path))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", requests
    server.shutdown()
    thread.join()
    server.server_close()


@pytest.fixture
def live_env(local_site, tmp_path):
    from browsergym.core.task import AbstractBrowserTask
    from webarena_pro_bgym.benchmark.env import WebArenaProEnvArgs

    url, requests = local_site

    class SmokeTask(AbstractBrowserTask):
        def __init__(self, seed):
            super().__init__(seed)
            self.navigation_guard = TaskNavigationGuard([url])

        def setup(self, page):
            self.navigation_guard.install(page)
            page.goto(url)
            return "Inspect the fixture", {}

        def validate(self, page, chat_messages, **kwargs):
            return 0, False, "", {}

        def teardown(self):
            pass

    config = SimpleNamespace(task_id="synthetic-recovery", sites=())
    env = WebArenaProEnvArgs(config, "smoke", enable_audio=False).make_env(tmp_path)
    env.task_entrypoint = SmokeTask
    env.task_kwargs = {}
    try:
        env.reset()
        yield env, url, requests
    finally:
        env.close()


@pytest.mark.skipif(os.getenv("WEBARENA_PRO_TEST_BROWSER") != "1", reason="opt-in live Chromium")
def test_live_external_same_tab_popup_and_local_navigation_error(live_env):
    env, url, requests = live_env
    for action in ("page.get_by_text('External', exact=True).click()",
                   "page.get_by_text('Restore Access', exact=True).click()"):
        obs, _, terminated, truncated, _ = env.step(action)
        assert not terminated and not truncated
        assert "Blocked navigation" in obs["last_action_error"]
        assert all(env.task.navigation_guard.is_allowed_page(page.url) for page in env.context.pages)
        assert not any(path in {"/outside", "/pricing"} for method, path in requests)
        # A blocked popup can be blank; explicitly restore the original tab.
        env.page = next(page for page in env.context.pages if page.url.startswith(url))
    obs, _, terminated, truncated, _ = env.step(f"page.goto('{url}/failed', timeout=1000)")
    assert not terminated and not truncated
    assert obs["last_action_error"]
    obs, _, terminated, truncated, _ = env.step("page.go_back()")
    assert not terminated and not truncated
    assert obs["url"].startswith(url)


@pytest.mark.skipif(os.getenv("WEBARENA_PRO_TEST_BROWSER") != "1", reason="opt-in live Chromium")
def test_live_renderer_recovery_preserves_context_and_never_replays_action(
    live_env, tmp_path, renderer_crash_action, monkeypatch,
):
    from webarena_pro_bgym.benchmark.browser_diagnostics import WebArenaProBrowserCrashError

    env, url, requests = live_env
    env.page.evaluate("localStorage.setItem('saved', 'yes'); sessionStorage.setItem('draft', 'yes')")
    env.context.add_cookies([{"name": "fixture", "value": "yes", "url": url}])
    context = env.context
    old_page = env.page
    unbounded_close = Mock(side_effect=AssertionError("Never call unbounded sync Page.close"))
    monkeypatch.setattr(old_page, "close", unbounded_close)
    action = "page.evaluate(\"fetch('/saved', {method: 'POST'})\")\n" + renderer_crash_action
    obs, _, terminated, truncated, _ = env.step(action)
    assert not terminated and not truncated
    assert env.context is context and env.page is not old_page
    unbounded_close.assert_not_called()
    assert old_page.is_closed() and old_page not in context.pages
    assert len(obs["open_pages_urls"]) == len(obs["open_pages_titles"]) == 1
    assert obs["active_page_index"].tolist() == [0]
    assert obs["url"].startswith(url)
    assert "not replayed" in obs["last_action_error"]
    assert "sessionStorage" in obs["last_action_error"]
    assert env.page.evaluate("localStorage.getItem('saved')") == "yes"
    assert any(cookie["name"] == "fixture" for cookie in env.context.cookies())
    assert requests.count(("POST", "/saved")) == 1
    reports = json.loads((tmp_path / "browser_recoveries.json").read_text())
    assert [report["status"] for report in reports] == ["restored"]
    # Tab actions, page settling, and observations must never revisit the dead
    # tab. These use the same context.pages list as BrowserGym's tab_focus.
    following, _, terminated, truncated, _ = env.step(
        "page = page.context.pages[0]\npage.bring_to_front()"
    )
    assert not terminated and not truncated
    assert len(following["open_pages_titles"]) == 1
    # The second renderer crash exhausts the per-episode allowance.
    with pytest.raises(WebArenaProBrowserCrashError) as raised:
        env.step(renderer_crash_action)
    assert raised.value.diagnostics["recovery_attempts"] == 1
