import inspect
import logging

import pytest

from webarena_pro_core.autologin import sync_api as auto_login
from webarena_pro_core.autologin.sync_api import AutoLogin
from webarena_pro_core import website_metadata
from webarena_pro_core.task import load_task_configs


class FakeLocator:
    def __init__(self, page, selector, *, count=1):
        self.page = page
        self.selector = selector
        self._count = count

    @property
    def first(self):
        return self

    def fill(self, value, **kwargs):
        self.page.calls.append(("fill", self.selector, value, kwargs))

    def click(self, **kwargs):
        self.page.calls.append(("click", self.selector, kwargs))

    def check(self, **kwargs):
        self.page.calls.append(("check", self.selector, kwargs))

    def press(self, key, **kwargs):
        self.page.calls.append(("press", self.selector, key, kwargs))

    def count(self):
        return self._count

    def or_(self, other):
        return self


class FakeContext:
    def __init__(self):
        self.pages = []

    def new_page(self):
        page = FakePage(context=self)
        self.pages.append(page)
        return page


class FakePage:
    def __init__(self, *, context=None):
        self.calls = []
        self.context = context or FakeContext()
        self.url = "about:blank"
        self.closed = False

    def goto(self, url, **kwargs):
        self.url = url
        self.calls.append(("goto", url, kwargs))

    def locator(self, selector):
        self.calls.append(("locator", selector))
        return FakeLocator(self, selector)

    def get_by_label(self, label, **kwargs):
        return FakeLocator(self, f"label:{label}")

    def get_by_placeholder(self, placeholder, **kwargs):
        return FakeLocator(self, f"placeholder:{placeholder}")

    def get_by_role(self, role, **kwargs):
        return FakeLocator(self, f"role:{role}:{kwargs.get('name')}")

    def get_by_text(self, text, **kwargs):
        return FakeLocator(self, f"text:{text}")

    def wait_for_load_state(self, state, **kwargs):
        self.calls.append(("wait_for_load_state", state, kwargs))

    def wait_for_url(self, url, **kwargs):
        self.calls.append(("wait_for_url", url, kwargs))

    def wait_for_function(self, expression, **kwargs):
        self.calls.append(("wait_for_function", expression, kwargs))

    def wait_for_selector(self, selector, **kwargs):
        self.calls.append(("wait_for_selector", selector, kwargs))

    def close(self):
        self.closed = True


def test_auto_login_module_does_not_import_browsergym():
    assert "browsergym" not in inspect.getsource(auto_login)


def test_deployed_website_url_honors_worker_env(monkeypatch):
    monkeypatch.setenv("WP_X_LITE_URL", "http://x-lite-w7.localhost")

    assert website_metadata.deployed_website_url("x-lite") == "http://x-lite-w7.localhost"
    assert website_metadata.deployed_website_login_url("x-lite") == "http://x-lite-w7.localhost/login"


def test_resolves_requested_credentials_and_jobportal_type():
    login = AutoLogin()

    assert login.resolve_credentials("x-lite", "airescientist") == (
        "airescientist",
        "password123",
    )
    assert login.resolve_jobportal_user_type("alice_seeker") == "job_seeker"
    assert login.resolve_jobportal_user_type("employer_acme") == "employer"


@pytest.mark.parametrize("requested", ["agent1", "agent1@test.com"])
@pytest.mark.parametrize(
    ("site", "expected_identifier"),
    [("mydrive", "agent1@test.com"), ("x-lite", "agent1")],
)
def test_resolves_both_credential_aliases_with_site_specific_identifier(
    requested, site, expected_identifier
):
    login = AutoLogin(
        credentials={
            site: [
                {"username": "other", "email": "other@test.com", "password": "other"},
                {"username": "agent1", "email": "agent1@test.com", "password": "password"},
            ]
        }
    )

    assert login.resolve_credentials(site, requested) == (expected_identifier, "password")


@pytest.mark.parametrize("site", ["mydrive", "x-lite"])
@pytest.mark.parametrize(
    "fields", [{"username": "agent1"}, {"email": "agent1@test.com"}]
)
def test_resolves_credentials_with_a_single_identifier(site, fields):
    login = AutoLogin(credentials={site: [{**fields, "password": "password"}]})
    identifier = next(iter(fields.values()))

    assert login.resolve_credentials(site) == (identifier, "password")
    assert login.resolve_credentials(site, identifier) == (identifier, "password")


@pytest.mark.parametrize("requested", ["unknown", "unknown@test.com", ""])
@pytest.mark.parametrize(
    "fields",
    [
        {"username": "agent1", "email": "agent1@test.com"},
        {"username": "", "email": "agent1@test.com"},
        {"username": "agent1", "email": ""},
    ],
)
def test_unknown_or_empty_identifiers_do_not_match_credentials(requested, fields):
    login = AutoLogin(credentials={"mydrive": [{**fields, "password": "password"}]})

    with pytest.raises(RuntimeError, match="No credentials found for username"):
        login.resolve_credentials("mydrive", requested)


@pytest.mark.parametrize("requested", [None, "agent1", "agent1@test.com"])
def test_mydrive_login_uses_email_for_default_username_and_email(requested):
    page = FakePage()
    login = AutoLogin(urls={"mydrive": "http://mydrive.local"})

    login.perform_login("mydrive", page, username=requested)

    assert (
        "fill",
        'input[autocomplete="email"], input[type="email"], input[name="email"]',
        "agent1@test.com",
        {},
    ) in page.calls
    assert ("click", "role:button:Log in", {}) in page.calls


def test_perform_login_uses_x_lite_flow():
    page = FakePage()
    login = AutoLogin(
        urls={"x-lite": "http://x-lite.local"},
        credentials={
            "x-lite": [
                {"username": "techvalueinvestor", "password": "password123"},
            ],
        },
    )

    login.perform_login("x-lite", page)

    assert ("goto", "http://x-lite.local/login", {"timeout": 30000}) in page.calls
    assert ("fill", '[data-test="login-username"]', "techvalueinvestor", {}) in page.calls
    assert ("fill", '[data-test="login-password"]', "password123", {}) in page.calls
    assert ("click", '[data-test="login-submit"]', {}) in page.calls


def test_perform_login_uses_mattermost_flow():
    page = FakePage()
    login = AutoLogin(
        urls={"mattermost": "http://mattermost.local"},
        credentials={
            "mattermost": [
                {"username": "john.doe", "password": "User@Secure123"},
            ],
        },
    )

    login.perform_login("mattermost", page)

    assert (
        "goto",
        "http://mattermost.local/login",
        {"timeout": 30000, "wait_until": "domcontentloaded"},
    ) in page.calls
    assert ("fill", "#input_loginId", "john.doe", {}) in page.calls
    assert ("fill", "#input_password-input", "User@Secure123", {}) in page.calls
    assert ("click", "#saveSetting", {}) in page.calls


def test_nextcloud_login_wait_accepts_canonical_default_port():
    page = FakePage()
    login = AutoLogin(urls={"nextcloud": "http://nextcloud:80"})
    login.perform_login("nextcloud", page)
    wait = next(call for call in page.calls if call[0] == "wait_for_url")
    predicate = wait[1]
    assert predicate("http://nextcloud/apps/dashboard/")
    assert predicate("http://nextcloud:80/apps/files/")
    assert not predicate("http://nextcloud/login")
    assert wait[2]["wait_until"] == "domcontentloaded"


def test_yt_lite_login_uses_authenticated_redirect_with_active_media_requests():
    class StreamingPage(FakePage):
        def wait_for_load_state(self, state, **kwargs):
            if state == "networkidle":
                raise TimeoutError("Video streams remain active")
            super().wait_for_load_state(state, **kwargs)

    page = StreamingPage()
    login = AutoLogin(urls={"yt-lite": "http://yt-lite:7860"})
    login.perform_login("yt-lite", page, username="seed_user")
    assert ("goto", "http://yt-lite:7860/login", {"timeout": 30000, "wait_until": "domcontentloaded"}) in page.calls
    assert ("wait_for_url", "http://yt-lite:7860/", {"timeout": 15000, "wait_until": "domcontentloaded"}) in page.calls


def test_mattermost_login_raises_when_form_never_appears():
    class NoMattermostFormPage(FakePage):
        def wait_for_function(self, expression, **kwargs):
            self.calls.append(("wait_for_function", expression, kwargs))
            raise TimeoutError("not ready")

        def locator(self, selector):
            self.calls.append(("locator", selector))
            count = 0 if selector == "#input_loginId" else 1
            return FakeLocator(self, selector, count=count)

        def get_by_text(self, text, **kwargs):
            return FakeLocator(self, f"text:{text}", count=0)

    page = NoMattermostFormPage()
    login = AutoLogin(
        urls={"mattermost": "http://mattermost.local"},
        credentials={
            "mattermost": [
                {"username": "john.doe", "password": "User@Secure123"},
            ],
        },
    )

    with pytest.raises(RuntimeError, match="Mattermost login form did not appear"):
        login.perform_login("mattermost", page)


def test_ui_login_uses_context_page_and_ready_callback():
    ready_sites = []
    root_page = FakePage()
    login = AutoLogin(
        urls={"x-lite": "http://x-lite.local"},
        credentials={
            "x-lite": [
                {"username": "techvalueinvestor", "password": "password123"},
            ],
        },
        wait_until_ready=ready_sites.append,
    )

    login.ui_login("x-lite", root_page, verify=False)

    assert ready_sites == ["x-lite"]
    assert len(root_page.context.pages) == 1
    assert root_page.context.pages[0].closed is True


def test_ui_login_logs_intermediate_retries_at_info(monkeypatch, caplog):
    root_page = FakePage()
    login = AutoLogin(
        urls={"x-lite": "http://x-lite.local"},
        credentials={
            "x-lite": [
                {"username": "techvalueinvestor", "password": "password123"},
            ],
        },
    )
    attempts = []

    def flaky_perform_login(site, page, username=None):
        attempts.append(site)
        if len(attempts) == 1:
            raise RuntimeError("still warming up")

    monkeypatch.setattr(login, "perform_login", flaky_perform_login)
    monkeypatch.setattr(login, "verify_login", lambda site, context: True)
    monkeypatch.setattr(auto_login.time, "sleep", lambda seconds: None)

    with caplog.at_level(logging.INFO, logger="webarena_pro_core.autologin.sync_api"):
        login.ui_login("x-lite", root_page)

    retry_records = [
        record
        for record in caplog.records
        if "UI login attempt 1/3 failed" in record.getMessage()
    ]
    assert len(retry_records) == 1
    assert retry_records[0].levelno == logging.INFO
    assert attempts == ["x-lite", "x-lite"]


@pytest.mark.parametrize("task_id", ["050", "056"])
def test_firefly_read_tasks_require_seeded_user_login(task_id):
    configs = {task.task_id: task for task in load_task_configs(split="test")}
    config = configs[task_id]

    assert config.sites == ("firefly",)
    assert config.require_login is True
    assert config.login_usernames == {"firefly": "test@example.com"}
    username, password = AutoLogin().resolve_credentials(
        "firefly", config.login_usernames["firefly"]
    )
    assert username == "test@example.com"
    assert password
    assert password not in config.intent
