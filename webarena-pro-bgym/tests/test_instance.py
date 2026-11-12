from webarena_pro_bgym.benchmark.instance import WebArenaProInstance


def test_instance_resolves_urls_from_current_environment(monkeypatch):
    monkeypatch.setenv("WP_NEXTCLOUD_URL", "http://localhost:4123")

    instance = WebArenaProInstance()

    assert instance.urls["nextcloud"] == "http://localhost:4123"
    assert instance.login_urls["nextcloud"] == "http://localhost:4123/login"


class DummyPage:
    def __init__(self, context):
        self.context = context

    def close(self):
        return None


class DummyContext:
    def __init__(self):
        self.created_pages = []

    def new_page(self):
        page = DummyPage(self)
        self.created_pages.append(page)
        return page


def test_ui_login_waits_for_readiness_before_attempt(monkeypatch):
    instance = WebArenaProInstance()
    context = DummyContext()
    root_page = DummyPage(context)
    call_order = []

    instance._auto_login.wait_until_ready = lambda site: call_order.append(("wait", site))
    instance._auto_login.perform_login = (
        lambda site, page, username=None: call_order.append(("perform", site, username))
    )
    instance._auto_login.verify_login = (
        lambda site, browser_context: call_order.append(("verify", site)) or True
    )

    instance.ui_login("nextcloud", root_page, max_attempts=1)

    assert call_order == [
        ("wait", "nextcloud"),
        ("perform", "nextcloud", None),
        ("verify", "nextcloud"),
    ]


def test_ui_login_retries_until_verification_succeeds(monkeypatch):
    instance = WebArenaProInstance()
    context = DummyContext()
    root_page = DummyPage(context)
    attempts = []
    verification_results = iter([False, False, True])

    instance._auto_login.wait_until_ready = lambda site: None
    instance._auto_login.perform_login = (
        lambda site, page, username=None: attempts.append((site, username))
    )
    instance._auto_login.verify_login = lambda site, browser_context: next(
        verification_results
    )
    monkeypatch.setattr(
        "webarena_pro_core.autologin.sync_api.time.sleep",
        lambda seconds: None,
    )

    instance.ui_login("mattermost", root_page, max_attempts=3)

    assert attempts == [
        ("mattermost", None),
        ("mattermost", None),
        ("mattermost", None),
    ]


def test_ui_login_passes_username_override(monkeypatch):
    instance = WebArenaProInstance()
    context = DummyContext()
    root_page = DummyPage(context)
    attempts = []

    instance._auto_login.wait_until_ready = lambda site: None
    instance._auto_login.perform_login = (
        lambda site, page, username=None: attempts.append((site, username))
    )
    instance._auto_login.verify_login = lambda site, browser_context: True

    instance.ui_login("mattermost", root_page, username="jane.smith", max_attempts=1)

    assert attempts == [("mattermost", "jane.smith")]


def test_resolve_passkey_uses_passkey_credentials():
    instance = WebArenaProInstance()

    assert instance._auto_login.resolve_passkey("flight-search") == "flyingagents"


def test_minerva_lite_login_url_and_credentials_are_configured():
    instance = WebArenaProInstance()

    assert instance.login_urls["minerva-lite"] == f"{instance.urls['minerva-lite']}/login"
    assert instance._auto_login.resolve_credentials("minerva-lite", None) == (
        "260123456",
        "mcgill123",
    )


class LocatorStub:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class FireflyLocatorStub:
    def __init__(self, page, selector, count):
        self.page = page
        self.selector = selector
        self._count = count

    def count(self):
        return self._count

    def fill(self, value, **_kwargs):
        self.page.filled.append((self.selector, value))

    def click(self, **kwargs):
        self.page.clicked.append((self.selector, kwargs))
        if self.page.click_sets_authenticated:
            self.page.url = self.page.base_url
        if self.page.click_error is not None:
            raise self.page.click_error


class FireflyLoginPage:
    def __init__(self, base_url, redirect_authenticated=False):
        self.base_url = base_url
        self.redirect_authenticated = redirect_authenticated
        self.url = "about:blank"
        self.visited_urls = []
        self.filled = []
        self.clicked = []
        self.click_error = None
        self.click_sets_authenticated = False

    def goto(self, url, **_kwargs):
        self.visited_urls.append(url)
        self.url = self.base_url if self.redirect_authenticated else url

    def wait_for_load_state(self, *_args, **_kwargs):
        return None

    def wait_for_function(self, *_args, **_kwargs):
        return None

    def locator(self, selector):
        on_login_page = self.url.rstrip("/").endswith("/login")
        count = 1 if on_login_page and selector in {
            'input[name="email"]',
            'input[name="password"]',
            'button[type="submit"]',
        } else 0
        return FireflyLocatorStub(self, selector, count)


class VerifyPage:
    def __init__(self, routes):
        self.routes = routes
        self.url = ""
        self.visited_urls = []

    def goto(self, url, **_kwargs):
        self.visited_urls.append(url)
        self.url = self.routes.get(url, url)

    def wait_for_load_state(self, *_args, **_kwargs):
        return None

    def get_by_label(self, label):
        if label == "Username or Email" and "/accounts/login/" in self.url:
            return LocatorStub(1)
        return LocatorStub(0)

    def get_by_role(self, role, name=None):
        if role == "button" and name == "Enter workspace" and "/login" in self.url:
            return LocatorStub(1)
        return LocatorStub(0)

    def get_by_text(self, text, exact=False):
        if text == "Deals" and "/deals" in self.url:
            return LocatorStub(1)
        return LocatorStub(0)

    def locator(self, selector):
        if selector == 'input[name="usr"], #login_email' and "/login" in self.url:
            return LocatorStub(1)
        if selector == '[data-test="login-student-id"]' and "/login" in self.url:
            return LocatorStub(1)
        if (
            selector
            == (
                '[data-test="sign-out"], '
                '[data-test="menu-home"], '
                '[data-test="menu-advisor"], '
                '[data-test="menu-student-home"]'
            )
            and "/login" not in self.url
        ):
            return LocatorStub(1)
        return LocatorStub(0)

    def close(self):
        return None


class VerifyContext:
    def __init__(self, page):
        self.page = page

    def new_page(self):
        return self.page


def test_jobportal_ui_login_verifies_dashboard_session():
    instance = WebArenaProInstance()
    base_url = instance.urls["jobportal"]
    page = VerifyPage(
        {
            f"{base_url}/dashboard/employer/": f"{base_url}/dashboard/employer/",
        }
    )
    context = VerifyContext(page)

    assert instance._auto_login.verify_login("jobportal", context)
    assert page.visited_urls == [f"{base_url}/dashboard/employer/"]


class FlightSearchVerifyPage(VerifyPage):
    def evaluate(self, _script):
        return True

    def locator(self, selector):
        if selector == '[data-testid="search-page"]':
            return LocatorStub(1)
        return LocatorStub(0)


def test_flight_search_ui_login_verifies_auth_and_search_page():
    instance = WebArenaProInstance()
    base_url = instance.urls["flight-search"]
    page = FlightSearchVerifyPage({base_url: base_url})
    context = VerifyContext(page)

    assert instance._auto_login.verify_login("flight-search", context)
    assert page.visited_urls == [base_url]


def test_firefly_ui_login_accepts_existing_authenticated_session():
    instance = WebArenaProInstance()
    base_url = instance.urls["firefly"]
    page = FireflyLoginPage(base_url, redirect_authenticated=True)

    instance._auto_login.perform_login("firefly", page)

    assert page.visited_urls == [f"{base_url}/login"]
    assert page.filled == []
    assert page.clicked == []


def test_firefly_ui_login_accepts_post_submit_navigation_timeout():
    instance = WebArenaProInstance()
    base_url = instance.urls["firefly"]
    page = FireflyLoginPage(base_url)
    page.click_sets_authenticated = True
    page.click_error = RuntimeError("click timed out while waiting for navigation")

    instance._auto_login.perform_login("firefly", page)

    assert page.filled == [
        ('input[name="email"]', "test@example.com"),
        ('input[name="password"]', "R9WrgT2vkn63TDBV"),
    ]
    assert page.clicked == [
        ('button[type="submit"]', {"timeout": 30000, "no_wait_after": True})
    ]


def test_jobportal_ui_login_verifies_jobseeker_dashboard_session():
    instance = WebArenaProInstance()
    base_url = instance.urls["jobportal"]
    page = VerifyPage(
        {
            f"{base_url}/dashboard/employer/": f"{base_url}/",
            f"{base_url}/dashboard/jobseeker/": f"{base_url}/dashboard/jobseeker/",
        }
    )
    context = VerifyContext(page)

    assert instance._auto_login.verify_login("jobportal", context)
    assert page.visited_urls == [
        f"{base_url}/dashboard/employer/",
        f"{base_url}/dashboard/jobseeker/",
    ]


def test_immich_ui_login_verifies_photos_session():
    instance = WebArenaProInstance()
    base_url = instance.urls["immich"]
    page = VerifyPage(
        {
            f"{base_url}/photos": f"{base_url}/photos",
        }
    )
    context = VerifyContext(page)

    assert instance._auto_login.verify_login("immich", context)
    assert page.visited_urls == [f"{base_url}/photos"]


def test_notion_ui_login_verifies_authenticated_app_session():
    instance = WebArenaProInstance()
    base_url = instance.urls["notion"]
    page = VerifyPage(
        {
            f"{base_url}/app": f"{base_url}/app/page/page_demo",
        }
    )
    context = VerifyContext(page)

    assert instance._auto_login.verify_login("notion", context)
    assert page.visited_urls == [f"{base_url}/app"]


def test_pipedrive_ui_login_verifies_deals_session():
    instance = WebArenaProInstance()
    base_url = instance.urls["pipedrive"]
    page = VerifyPage(
        {
            f"{base_url}/deals": f"{base_url}/deals",
        }
    )
    context = VerifyContext(page)

    assert instance._auto_login.verify_login("pipedrive", context)
    assert page.visited_urls == [f"{base_url}/deals"]


def test_erp_next_ui_login_verifies_app_session():
    instance = WebArenaProInstance()
    base_url = instance.urls["erp-next"]
    page = VerifyPage(
        {
            f"{base_url}/app/home": f"{base_url}/app/home",
        }
    )
    context = VerifyContext(page)

    assert instance._auto_login.verify_login("erp-next", context)
    assert page.visited_urls == [f"{base_url}/app/home"]


class ErpNextAppPageWithTextInput(VerifyPage):
    def locator(self, selector):
        if selector == 'input[type="text"]' and "/app/home" in self.url:
            return LocatorStub(1)
        return super().locator(selector)


def test_erp_next_ui_login_ignores_app_text_inputs():
    instance = WebArenaProInstance()
    base_url = instance.urls["erp-next"]
    page = ErpNextAppPageWithTextInput(
        {
            f"{base_url}/app/home": f"{base_url}/app/home",
        }
    )
    context = VerifyContext(page)

    assert instance._auto_login.verify_login("erp-next", context)


class ErpNextSetupWizardPage(VerifyPage):
    def get_by_text(self, text, exact=False):
        if text in {"Your Language", "Select Language"}:
            return LocatorStub(1)
        return super().get_by_text(text, exact=exact)


def test_erp_next_ui_login_rejects_language_setup_wizard():
    instance = WebArenaProInstance()
    base_url = instance.urls["erp-next"]
    page = ErpNextSetupWizardPage({f"{base_url}/app/home": f"{base_url}/app/home"})
    context = VerifyContext(page)

    assert not instance._auto_login.verify_login("erp-next", context)
    assert page.visited_urls == [f"{base_url}/app/home"]


def test_minerva_lite_ui_login_verifies_authenticated_shell():
    instance = WebArenaProInstance()
    base_url = instance.urls["minerva-lite"]
    page = VerifyPage({base_url: base_url})
    context = VerifyContext(page)

    assert instance._auto_login.verify_login("minerva-lite", context)
    assert page.visited_urls == [base_url]
