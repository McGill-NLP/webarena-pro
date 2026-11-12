"""Synchronous Playwright login flows for WebArena-Pro websites."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from ._shared import (
    AutoLoginConfig, CredentialStore, ReadyCallback,
    LOGIN_MAX_ATTEMPTS, LOGIN_RETRY_DELAY_SECONDS, LOGIN_VERIFY_TIMEOUT_MS,
    PENPOT_LOGIN_FORM_TIMEOUT_MS, _normalize_url_path, _mattermost_login_finished,
)

logger = logging.getLogger(__name__)

class AutoLogin(AutoLoginConfig):
    def page_shows_login_form(self, site: str, page: Any) -> bool:
        match site:
            case "mattermost":
                return page.locator("#input_loginId").count() > 0
            case "nextcloud":
                return page.get_by_label("Account name or email").count() > 0
            case "jobportal":
                return page.get_by_label("Username or Email").count() > 0
            case "thunderbird":
                return page.locator("#rcmloginuser").count() > 0
            case "firefly":
                return page.locator('input[name="email"]').count() > 0
            case "travelmap":
                return page.get_by_placeholder("name@example.com").count() > 0
            case "immich":
                return page.locator('input[name="email"]').count() > 0
            case "metabase":
                return page.get_by_placeholder("nicetoseeyou@email.com").count() > 0
            case "mydrive":
                return (
                    page.locator(
                        'input[autocomplete="email"], '
                        'input[type="email"], '
                        'input[name="email"]'
                    ).count()
                    > 0
                )
            case "notion":
                return page.get_by_role("button", name="Enter workspace").count() > 0
            case "x-lite":
                return page.locator('[data-test="login-username"]').count() > 0
            case "minerva-lite":
                return page.locator('[data-test="login-student-id"]').count() > 0
            case "acidwave":
                return page.locator('input[name="username"]').count() > 0
            case "password-manager":
                return page.get_by_placeholder("Enter your username").count() > 0
            case "peppermint":
                return page.get_by_label("Email address").count() > 0
            case "penpot":
                return page.locator('input[type="email"], input[name="email"]').count() > 0
            case "pipedrive":
                return page.get_by_label("Email").count() > 0
            case "erp-next":
                return page.locator('input[name="usr"], #login_email').count() > 0
            case "flight-search" | "yt-lite":
                return False
            case _:
                return False

    @staticmethod
    def flight_search_auth_ok(page: Any) -> bool:
        try:
            return bool(
                page.evaluate(
                    """async () => {
                        const response = await fetch('/api/auth/check', {
                            credentials: 'include',
                        });
                        return response.ok;
                    }"""
                )
            )
        except Exception:
            return False

    def firefly_auth_ok(self, page: Any) -> bool:
        parsed = urlparse(page.url)
        if parsed.scheme not in {"http", "https"}:
            return False
        return (
            _normalize_url_path(page.url) != "/login"
            and not self.page_shows_login_form("firefly", page)
        )

    def verify_login(self, site: str, context: Any) -> bool:
        if site == "flight-search":
            verify_page = context.new_page()
            try:
                verify_page.goto(
                    self.urls[site], timeout=30000, wait_until="domcontentloaded"
                )
                _wait_for_networkidle(verify_page)
                return self.flight_search_auth_ok(verify_page) and (
                    verify_page.locator('[data-testid="search-page"]').count() > 0
                )
            finally:
                verify_page.close()

        if site == "x-lite":
            return self._verify_authenticated_ui(
                site,
                context,
                self.urls[site],
                '[data-testid="nav-profile"], '
                '[data-test="post-tweet-textarea"], '
                'a[href="/logout"]',
            )

        if site == "acidwave":
            verify_page = context.new_page()
            try:
                verify_page.goto(
                    self.urls[site], timeout=30000, wait_until="domcontentloaded"
                )
                _wait_for_networkidle(verify_page)
                current_user = verify_page.evaluate(
                    "() => localStorage.getItem('acidwave_current_user')"
                )
                return bool(current_user) and (
                    verify_page.get_by_text("AUTHENTICATED").count() > 0
                )
            finally:
                verify_page.close()

        if site == "travelmap":
            return self._verify_role_ui(
                site,
                context,
                self.urls[site],
                role="button",
                name="Log Out",
            )

        if site == "minerva-lite":
            return self._verify_path_and_ui(
                site,
                context,
                self.urls[site],
                path_prefixes=("/",),
                authenticated_selector=(
                    '[data-test="sign-out"], '
                    '[data-test="menu-home"], '
                    '[data-test="menu-advisor"], '
                    '[data-test="menu-student-home"]'
                ),
                reject_login_path=True,
            )

        if site == "peppermint":
            verify_page = context.new_page()
            try:
                verify_page.goto(
                    self.urls[site], timeout=30000, wait_until="domcontentloaded"
                )
                _wait_for_networkidle(verify_page)
                return any(
                    verify_page.get_by_text(label, exact=True).count() > 0
                    for label in ("New Issue", "Dashboard", "James Carter")
                )
            finally:
                verify_page.close()

        if site == "immich":
            return self._verify_path_and_ui(
                site,
                context,
                f"{self.urls[site]}/photos",
                path_prefixes=("/photos",),
            )

        if site == "jobportal":
            verify_page = context.new_page()
            try:
                for dashboard_path in ("/dashboard/employer", "/dashboard/jobseeker"):
                    verify_page.goto(
                        f"{self.urls[site]}{dashboard_path}/",
                        timeout=30000,
                        wait_until="domcontentloaded",
                    )
                    _wait_for_networkidle(verify_page)
                    if _normalize_url_path(verify_page.url) == dashboard_path:
                        return True
                return False
            finally:
                verify_page.close()

        if site == "notion":
            return self._verify_path_and_ui(
                site,
                context,
                f"{self.urls[site]}/app",
                path_prefixes=("/app",),
                reject_login_form=True,
            )

        if site == "mydrive":
            return self._verify_path_and_ui(
                site,
                context,
                f"{self.urls[site]}/drive",
                path_prefixes=("/drive",),
                authenticated_text="Sign Out",
                reject_login_form=True,
            )

        if site == "pipedrive":
            return self._verify_path_and_ui(
                site,
                context,
                f"{self.urls[site]}/deals",
                path_prefixes=("/deals",),
                authenticated_text="Deals",
                reject_login_path=True,
                reject_login_form=True,
            )

        if site == "erp-next":
            return self._verify_path_and_ui(
                site,
                context,
                f"{self.urls[site]}/app/home",
                path_prefixes=("/app",),
                reject_login_form=True,
                reject_setup_wizard=True,
            )

        if site == "penpot":
            verify_page = context.new_page()
            try:
                verify_page.goto(
                    f"{self.urls[site]}/#/dashboard",
                    timeout=30000,
                    wait_until="domcontentloaded",
                )
                _wait_for_networkidle(verify_page)
                try:
                    verify_page.wait_for_function(
                        "() => window.location.hash.includes('/dashboard') "
                        "|| window.location.hash.includes('/auth/login')",
                        timeout=LOGIN_VERIFY_TIMEOUT_MS,
                    )
                except Exception:
                    return False
                return "#/dashboard" in verify_page.url and not self.page_shows_login_form(
                    site, verify_page
                )
            finally:
                verify_page.close()

        login_url = self.login_urls.get(site)
        if not login_url:
            return True

        verify_page = context.new_page()
        try:
            verify_page.goto(login_url, timeout=30000, wait_until="domcontentloaded")
            _wait_for_networkidle(verify_page)
            current_path = _normalize_url_path(verify_page.url)
            login_path = _normalize_url_path(login_url)
            return not (
                current_path == login_path
                and self.page_shows_login_form(site, verify_page)
            )
        finally:
            verify_page.close()

    def perform_login(
        self,
        site: str,
        page: Any,
        username: str | None = None,
    ) -> None:
        url = self.urls[site]

        match site:
            case "mattermost":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(f"{url}/login", timeout=30000, wait_until="domcontentloaded")
                try:
                    page.wait_for_function(
                        "() => window.location.pathname.startsWith('/landing') "
                        "|| document.querySelector('#input_loginId') !== null",
                        timeout=60000,
                    )
                except Exception:
                    pass
                if "/landing" in page.url or page.get_by_text("View in Browser").count() > 0:
                    # The landing URL can appear before its control has rendered.
                    # Let click wait for any supported control instead of choosing
                    # a fallback from counts taken while the page is still empty.
                    view_in_browser = (
                        page.get_by_text("View in Browser")
                        .or_(page.get_by_role("link", name="View in Browser"))
                        .or_(page.get_by_role("button", name="View in Browser"))
                    )
                    view_in_browser.first.click(timeout=15000)
                    page.wait_for_selector("#input_loginId", timeout=30000)
                if page.locator("#input_loginId").count() == 0:
                    _wait_for_networkidle(page)
                    if page.locator("#input_loginId").count() == 0:
                        raise RuntimeError(
                            "Mattermost login form did not appear at "
                            f"{page.url}; the app may still be warming up."
                        )
                page.locator("#input_loginId").fill(username)
                page.locator("#input_password-input").fill(password)
                page.locator("#saveSetting").click()
                page.wait_for_url(
                    _mattermost_login_finished,
                    timeout=30000,
                    wait_until="domcontentloaded",
                )

            case "nextcloud":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(f"{url}/login", timeout=60000, wait_until="domcontentloaded")
                page.wait_for_load_state("domcontentloaded")
                page.get_by_label("Account name or email").fill(username, timeout=30000)
                page.get_by_label("Password", exact=True).fill(password, timeout=30000)
                page.get_by_role("button", name="Log in", exact=True).click(timeout=30000)
                # Chromium removes an explicit default port (e.g. :80) from
                # navigations. Wait for the authenticated application path,
                # rather than a glob that can never match the canonical URL.
                page.wait_for_url(
                    lambda actual: _normalize_url_path(str(actual)).startswith("/apps/"),
                    timeout=60000,
                    wait_until="domcontentloaded",
                )

            case "flight-search":
                passkey = self.resolve_passkey(site)
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                _wait_for_networkidle(page)
                if self.flight_search_auth_ok(page):
                    return
                page.get_by_placeholder("Passkey").fill(passkey, timeout=15000)
                page.get_by_role("button", name="Continue").click(timeout=15000)
                page.wait_for_function(
                    """async () => {
                        const response = await fetch('/api/auth/check', {
                            credentials: 'include',
                        });
                        return response.ok;
                    }""",
                    timeout=15000,
                )
                page.wait_for_selector('[data-testid="search-page"]', timeout=15000)

            case "jobportal":
                username, password = self.resolve_credentials(site, username=username)
                user_type = self.resolve_jobportal_user_type(username)
                dashboard_path = "jobseeker" if user_type == "job_seeker" else "employer"
                page.goto(f"{url}/accounts/login/", timeout=30000)
                page.wait_for_load_state("networkidle")
                page.locator(f'input[name="user_type"][value="{user_type}"]').check()
                page.get_by_label("Username or Email").fill(username)
                page.get_by_label("Password").fill(password)
                page.get_by_label("Remember me").check()
                page.get_by_role("button", name="Sign In").click()
                page.wait_for_url(
                    f"{url}/dashboard/{dashboard_path}/",
                    timeout=15000,
                    wait_until="domcontentloaded",
                )

            case "thunderbird":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(url, timeout=60000)
                page.wait_for_load_state("networkidle")
                page.locator("#rcmloginuser").fill(username)
                page.locator("#rcmloginpwd").fill(password)
                page.locator("#rcmloginsubmit").click()
                page.wait_for_load_state("networkidle")

            case "firefly":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(f"{url}/login", timeout=30000, wait_until="domcontentloaded")
                _wait_for_networkidle(page)
                if self.firefly_auth_ok(page):
                    return
                page.locator('input[name="email"]').fill(username, timeout=30000)
                page.locator('input[name="password"]').fill(password, timeout=30000)
                submit_button = page.locator('button[type="submit"]')
                try:
                    submit_button.click(timeout=30000, no_wait_after=True)
                    page.wait_for_function(
                        "() => window.location.pathname !== '/login'",
                        timeout=30000,
                    )
                except Exception:
                    if self.firefly_auth_ok(page):
                        return
                    raise

            case "travelmap":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(url, timeout=30000)
                page.wait_for_load_state("networkidle")
                page.get_by_role("link", name="Sign In").click()
                page.wait_for_load_state("networkidle")
                page.get_by_placeholder("name@example.com").fill(username)
                page.get_by_placeholder("Enter your password").fill(password)
                page.get_by_role("button", name="Sign In").click()
                page.wait_for_url(f"{url}/**", timeout=15000)

            case "immich":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(f"{url}/auth/login", timeout=30000)
                page.wait_for_load_state("networkidle")
                page.get_by_label("Email").fill(username)
                page.get_by_label("Password").fill(password)
                page.get_by_role("button", name="Login").click()
                page.wait_for_url(f"{url}/**", timeout=15000)

            case "metabase":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(f"{url}/auth/login", timeout=30000)
                page.wait_for_load_state("networkidle")
                page.get_by_placeholder("nicetoseeyou@email.com").fill(username)
                page.get_by_placeholder("Shhh...").fill(password)
                page.get_by_role("button", name="Sign in").click()

            case "mydrive":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(f"{url}/login", timeout=30000, wait_until="domcontentloaded")
                _wait_for_networkidle(page)
                page.locator(
                    'input[autocomplete="email"], '
                    'input[type="email"], '
                    'input[name="email"]'
                ).first.fill(username)
                page.locator(
                    'input[autocomplete="current-password"], '
                    'input[type="password"], '
                    'input[name="password"]'
                ).first.fill(password)
                login_button = page.get_by_role("button", name="Log in")
                if login_button.count() == 0:
                    login_button = page.get_by_role("button", name="Sign in")
                login_button.first.click()
                page.wait_for_function(
                    "() => window.location.pathname.startsWith('/drive')",
                    timeout=15000,
                )

            case "notion":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(f"{url}/login", timeout=30000, wait_until="domcontentloaded")
                page.locator('input[type="email"]').fill(username, timeout=30000)
                page.locator('input[type="password"]').fill(password, timeout=30000)
                with page.expect_response(
                    lambda response: response.url.endswith("/api/login")
                    and response.request.method == "POST",
                    timeout=15000,
                ) as login_response:
                    page.get_by_role("button", name="Enter workspace").click(
                        timeout=30000
                    )
                if not login_response.value.ok:
                    raise RuntimeError(
                        f"Notion login failed with HTTP {login_response.value.status}"
                    )
                page.wait_for_function(
                    "() => window.location.pathname.startsWith('/app')",
                    timeout=15000,
                )

            case "yt-lite":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(f"{url}/login", timeout=30000, wait_until="domcontentloaded")
                page.locator('input[name="username"]').fill(username)
                page.locator('input[name="password"]').fill(password)
                page.locator('input[name="password"]').press("Enter")
                # Video requests can stay active after successful login. The
                # authenticated redirect is the readiness condition we need.
                page.wait_for_url(f"{url}/", timeout=15000, wait_until="domcontentloaded")

            case "x-lite":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(f"{url}/login", timeout=30000)
                page.locator('[data-test="login-username"]').fill(username)
                page.locator('[data-test="login-password"]').fill(password)
                page.locator('[data-test="login-submit"]').click()
                page.wait_for_load_state("networkidle")

            case "acidwave":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                _wait_for_networkidle(page)
                if page.evaluate(
                    "() => localStorage.getItem('acidwave_current_user') !== null"
                ):
                    return
                if page.locator('input[name="username"]').count() == 0:
                    page.get_by_text("CLICK_TO_LOGIN").click(timeout=15000)
                    page.wait_for_selector('input[name="username"]', timeout=15000)
                page.locator('input[name="username"]').fill(username)
                page.locator('input[name="password"]').fill(password)
                page.locator('input[name="password"]').press("Enter")
                page.wait_for_function(
                    "() => localStorage.getItem('acidwave_current_user') !== null",
                    timeout=15000,
                )

            case "minerva-lite":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(f"{url}/login", timeout=30000, wait_until="domcontentloaded")
                _wait_for_networkidle(page)
                page.locator('[data-test="login-student-id"]').fill(username)
                page.locator('[data-test="login-password"]').fill(password)
                page.locator('[data-test="login-submit"]').click()
                page.wait_for_function(
                    "() => !window.location.pathname.startsWith('/login')",
                    timeout=15000,
                )

            case "password-manager":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(url, timeout=30000)
                page.wait_for_load_state("networkidle")
                page.get_by_placeholder("Enter your username").fill(username)
                page.get_by_placeholder("Enter your master password").fill(password)
                page.get_by_role("button", name="Log in").click()
                page.wait_for_load_state("networkidle")

            case "peppermint":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(f"{url}/auth/login", timeout=30000)
                page.wait_for_load_state("networkidle")
                page.get_by_label("Email address").fill(username)
                page.get_by_label("Password").fill(password)
                with page.expect_response(
                    lambda response: response.url.endswith("/api/v1/auth/login")
                    and response.request.method == "POST",
                    timeout=15000,
                ) as login_response:
                    page.get_by_role("button", name="Sign In").click()
                if not login_response.value.ok:
                    raise RuntimeError(
                        f"Peppermint login failed with HTTP {login_response.value.status}"
                    )
                # The redirect follows token storage. Matching the login page
                # itself lets verification race the client's response handler.
                page.wait_for_url(
                    lambda actual: _normalize_url_path(str(actual)) != "/auth/login",
                    timeout=15000,
                    wait_until="domcontentloaded",
                )

            case "penpot":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(
                    f"{url}/#/auth/login",
                    timeout=60000,
                    wait_until="domcontentloaded",
                )
                _wait_for_networkidle(page, timeout=10000)
                email_selector = (
                    'input[type="email"], '
                    'input[name="email"], '
                    "#email, "
                    'input[placeholder*="email" i]'
                )
                password_selector = (
                    'input[type="password"], '
                    'input[name="password"], '
                    "#password"
                )
                page.wait_for_selector(
                    email_selector,
                    state="visible",
                    timeout=PENPOT_LOGIN_FORM_TIMEOUT_MS,
                )
                page.wait_for_selector(
                    password_selector,
                    state="visible",
                    timeout=PENPOT_LOGIN_FORM_TIMEOUT_MS,
                )
                page.locator(email_selector).first.fill(
                    username,
                    timeout=PENPOT_LOGIN_FORM_TIMEOUT_MS,
                )
                page.locator(password_selector).first.fill(
                    password,
                    timeout=PENPOT_LOGIN_FORM_TIMEOUT_MS,
                )
                login_button = page.get_by_role("button", name="Log in")
                if login_button.count() == 0:
                    login_button = page.get_by_role("button", name="Sign in")
                if login_button.count() == 0:
                    login_button = page.get_by_role("button", name="Login")
                if login_button.count() == 0:
                    login_button = page.get_by_role("button", name="Continue")
                if login_button.count() == 0:
                    login_button = page.locator('button[type="submit"]')
                login_button.first.click(timeout=30000)
                page.wait_for_function(
                    "() => window.location.hash.includes('/dashboard')",
                    timeout=30000,
                )

            case "pipedrive":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(f"{url}/login", timeout=30000)
                page.wait_for_load_state("networkidle")
                page.get_by_label("Email").fill(username)
                page.get_by_label("Password").fill(password)
                page.get_by_role("button", name="Sign in").click()
                page.wait_for_function(
                    "() => window.location.pathname !== '/login'",
                    timeout=15000,
                )

            case "erp-next":
                username, password = self.resolve_credentials(site, username=username)
                page.goto(f"{url}/login?redirect-to=/app/home", timeout=30000)
                page.wait_for_load_state("networkidle")
                page.locator(
                    'input[name="usr"], #login_email, input[type="text"]'
                ).first.fill(username)
                page.locator(
                    'input[name="pwd"], #login_password, input[type="password"]'
                ).first.fill(password)
                login_button = page.get_by_role("button", name="Login")
                if login_button.count() == 0:
                    login_button = page.locator('button[type="submit"], .btn-login')
                login_button.first.click()
                page.wait_for_url(
                    f"{url}/app/home",
                    timeout=30000,
                    wait_until="domcontentloaded",
                )

            case _:
                raise ValueError(f"Unknown site: {site}")

    def ui_login(
        self,
        site: str,
        page: Any,
        username: str | None = None,
        max_attempts: int = LOGIN_MAX_ATTEMPTS,
        verify: bool = True,
    ) -> None:
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            login_page = page.context.new_page()
            try:
                if self.wait_until_ready is not None:
                    self.wait_until_ready(site)
                self.perform_login(site, login_page, username=username)
                if not verify or self.verify_login(site, login_page.context):
                    logger.info("Verified UI login for %s on attempt %d", site, attempt)
                    return
                last_error = RuntimeError(f"Login verification failed for site '{site}'")
            except Exception as exc:
                last_error = exc
                log_login_retry = logger.warning if attempt == max_attempts else logger.info
                log_login_retry(
                    "UI login attempt %d/%d failed for %s: %s",
                    attempt,
                    max_attempts,
                    site,
                    exc,
                )
            finally:
                login_page.close()

            if attempt < max_attempts:
                time.sleep(LOGIN_RETRY_DELAY_SECONDS)

        if last_error is None:
            raise RuntimeError(f"UI login failed for site '{site}'")
        raise RuntimeError(
            f"UI login failed for site '{site}' after {max_attempts} attempts"
        ) from last_error

    def save_storage_state(
        self,
        site: str,
        path: str | Path,
        *,
        username: str | None = None,
        browser_name: str = "chromium",
        headless: bool = True,
        max_attempts: int = LOGIN_MAX_ATTEMPTS,
    ) -> Path:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise RuntimeError(
                "save_storage_state requires Playwright, a Core dependency. Install "
                "`webarena-pro-core` and run `playwright install chromium` "
                "before using this helper."
            ) from error

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser_type = getattr(playwright, browser_name)
            browser = browser_type.launch(headless=headless)
            try:
                context = browser.new_context()
                page = context.new_page()
                self.ui_login(
                    site,
                    page,
                    username=username,
                    max_attempts=max_attempts,
                )
                context.storage_state(path=str(output_path))
            finally:
                browser.close()
        return output_path

    def _verify_authenticated_ui(
        self,
        site: str,
        context: Any,
        url: str,
        authenticated_selector: str,
    ) -> bool:
        verify_page = context.new_page()
        try:
            verify_page.goto(url, timeout=30000, wait_until="domcontentloaded")
            _wait_for_networkidle(verify_page)
            return verify_page.locator(authenticated_selector).count() > 0
        finally:
            verify_page.close()

    def _verify_role_ui(
        self,
        site: str,
        context: Any,
        url: str,
        *,
        role: str,
        name: str,
    ) -> bool:
        verify_page = context.new_page()
        try:
            verify_page.goto(url, timeout=30000, wait_until="domcontentloaded")
            _wait_for_networkidle(verify_page)
            return verify_page.get_by_role(role, name=name).count() > 0
        finally:
            verify_page.close()

    def _verify_path_and_ui(
        self,
        site: str,
        context: Any,
        url: str,
        *,
        path_prefixes: tuple[str, ...],
        authenticated_selector: str | None = None,
        authenticated_text: str | None = None,
        reject_login_path: bool = False,
        reject_login_form: bool = False,
        reject_setup_wizard: bool = False,
    ) -> bool:
        verify_page = context.new_page()
        try:
            verify_page.goto(url, timeout=30000, wait_until="domcontentloaded")
            _wait_for_networkidle(verify_page)
            current_path = _normalize_url_path(verify_page.url)
            if reject_login_path and current_path.startswith("/login"):
                return False
            if not any(current_path.startswith(prefix) for prefix in path_prefixes):
                return False
            if reject_setup_wizard and (
                "setup-wizard" in current_path
                or any(
                    verify_page.get_by_text(label, exact=True).count() > 0
                    for label in ("Your Language", "Select Language")
                )
            ):
                return False
            if reject_login_form and self.page_shows_login_form(site, verify_page):
                return False
            if authenticated_selector and verify_page.locator(authenticated_selector).count() == 0:
                return False
            if authenticated_text and verify_page.get_by_text(
                authenticated_text, exact=True
            ).count() == 0:
                return False
            return True
        finally:
            verify_page.close()


def _wait_for_networkidle(page: Any, *, timeout: int = 5000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


def ui_login(
    site: str,
    page: Any,
    *,
    username: str | None = None,
    max_attempts: int = LOGIN_MAX_ATTEMPTS,
    verify: bool = True,
    urls: Mapping[str, str] | None = None,
    login_urls: Mapping[str, str] | None = None,
    credentials: CredentialStore | None = None,
    wait_until_ready: ReadyCallback | None = None,
) -> None:
    AutoLogin(
        urls=urls,
        login_urls=login_urls,
        credentials=credentials,
        wait_until_ready=wait_until_ready,
    ).ui_login(
        site,
        page,
        username=username,
        max_attempts=max_attempts,
        verify=verify,
    )


def save_storage_state(
    site: str,
    path: str | Path,
    *,
    username: str | None = None,
    browser_name: str = "chromium",
    headless: bool = True,
    max_attempts: int = LOGIN_MAX_ATTEMPTS,
    urls: Mapping[str, str] | None = None,
    login_urls: Mapping[str, str] | None = None,
    credentials: CredentialStore | None = None,
    wait_until_ready: ReadyCallback | None = None,
) -> Path:
    return AutoLogin(
        urls=urls,
        login_urls=login_urls,
        credentials=credentials,
        wait_until_ready=wait_until_ready,
    ).save_storage_state(
        site,
        path,
        username=username,
        browser_name=browser_name,
        headless=headless,
        max_attempts=max_attempts,
    )
