"""Shared helpers for the opt-in real-browser regression tests."""

import pytest


@pytest.fixture
def renderer_crash_action():
    # chrome://crash aborts navigation before the renderer has necessarily
    # exited. Wait for the real crash event before post_step extracts an
    # observation. Otherwise extraction can race the dying renderer on Linux.
    # Fail outside BrowserGym's ordinary action-error handler if injection
    # itself fails, rather than continuing into an unresponsive page.
    return """
import pytest
from playwright.sync_api import Error, TimeoutError
try:
    with page.expect_event("crash", timeout=10000):
        try:
            page.goto("chrome://crash", timeout=3000)
        except Error:
            pass
except TimeoutError:
    pytest.fail("Chromium did not report the injected renderer crash within 10 seconds")
"""
