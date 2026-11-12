"""Metabase authentication helpers."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

LOGIN_URL_PATH = "/auth/login"
EMAIL_SELECTOR = 'input[name="username"], input[type="email"], #username'
PASSWORD_SELECTOR = 'input[name="password"], input[type="password"], #password'
SUBMIT_SELECTOR = 'button[type="submit"], .Button--primary'


def login_to_metabase(
    page: "Page",
    metabase_url: str,
    username: str,
    password: str,
    timeout: int = 30000,
) -> bool:
    """Log into Metabase using the provided credentials.

    Args:
        page: Playwright page instance.
        metabase_url: Base URL of the Metabase instance.
        username: Email/username for login.
        password: Password for login.
        timeout: Maximum time to wait for login to complete (ms).

    Returns:
        True if login was successful, False otherwise.
    """
    login_url = f"{metabase_url.rstrip('/')}{LOGIN_URL_PATH}"

    current_url = page.url
    if LOGIN_URL_PATH not in current_url:
        logger.info(f"Navigating to login page: {login_url}")
        page.goto(login_url)

    try:
        page.wait_for_selector(EMAIL_SELECTOR, timeout=timeout)

        logger.debug("Filling in credentials")
        page.fill(EMAIL_SELECTOR, username)
        page.fill(PASSWORD_SELECTOR, password)

        logger.debug("Submitting login form")
        page.click(SUBMIT_SELECTOR)

        page.wait_for_url(
            lambda url: LOGIN_URL_PATH not in url,
            timeout=timeout,
        )

        logger.info("Login successful")
        return True

    except Exception as e:
        logger.error(f"Login failed: {e}")
        return False


def is_logged_in(page: "Page") -> bool:
    """Check if the user is currently logged in.

    Args:
        page: Playwright page instance.

    Returns:
        True if logged in, False otherwise.
    """
    url = page.url.lower()

    if "/auth/login" in url or "/setup" in url:
        return False

    logged_in_indicators = [
        page.locator('[data-testid="main-navbar"]').count() > 0,
        page.locator('.Nav').count() > 0,
        "/collection/" in url,
        "/dashboard/" in url,
        "/question/" in url,
    ]

    return any(logged_in_indicators)
