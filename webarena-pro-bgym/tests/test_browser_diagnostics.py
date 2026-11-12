"""Crash contract tests; opt-in browser tests use a real Chromium renderer."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
import time
from types import SimpleNamespace

import pytest
from playwright.sync_api import Error as PlaywrightError

from webarena_pro_bgym.benchmark.browser_diagnostics import (
    BrowserCrashMonitor,
    WebArenaProBrowserCrashError,
    _close_crashed_page,
    browser_operation,
    is_renderer_crash,
)
from webarena_pro_bgym.benchmark.env import (
    WebArenaProBrowserEnv,
    WebArenaProEnv,
    WebArenaProEnvArgs,
)
from webarena_pro_bgym.study import is_fatal_worker_error


@pytest.mark.parametrize("message", [
    "Frame.evaluate: Target crashed",
    "Page.screenshot: Target crashed",
    "Page.goto: Page crashed",
])
def test_classifies_playwright_renderer_errors_and_wrapped_causes(message):
    error = PlaywrightError(message)
    wrapped = RuntimeError("observation failed")
    wrapped.__cause__ = error
    assert is_renderer_crash(error)
    assert is_renderer_crash(wrapped)


@pytest.mark.parametrize("error", [
    PlaywrightError("Target page, context or browser has been closed"),
    PlaywrightError("Frame was detached"),
    PlaywrightError("Execution context was destroyed"),
    PlaywrightError("Timeout 30000ms exceeded"),
    PlaywrightError("Page.evaluate: Error: Target crashed"),
    RuntimeError("Target crashed"),
])
def test_does_not_classify_unrelated_errors_as_renderer_crashes(error):
    assert not is_renderer_crash(error)


def _env(tmp_path):
    return SimpleNamespace(
        env_args=SimpleNamespace(task_config=SimpleNamespace(task_id="413", sites=("metabase",))),
        page=SimpleNamespace(url="http://user:password@localhost:3000/question/notebook?token=secret#query"),
        steps_taken=2,
        browser_diagnostics_dir=tmp_path,
    )


def test_observation_failure_is_saved_with_context_and_never_retried(monkeypatch, tmp_path):
    env = WebArenaProEnv.__new__(WebArenaProEnv)
    env.__dict__.update(_env(tmp_path).__dict__)
    calls = []

    def crashed(self):
        calls.append("observation")
        raise PlaywrightError("Frame.evaluate: Target crashed")

    monkeypatch.setattr("browsergym.core.env.BrowserEnv._get_obs", crashed)
    with pytest.raises(WebArenaProBrowserCrashError) as raised:
        env._get_obs()
    with pytest.raises(WebArenaProBrowserCrashError):
        env.step("page.click('button')")
    with pytest.raises(WebArenaProBrowserCrashError):
        env.reset()
    assert calls == ["observation"]
    report = json.loads((tmp_path / "browser_failure.json").read_text())
    assert report == raised.value.diagnostics
    assert report["error_type"] == "environment_error"
    assert report["operation"] == "observation"
    assert report["task_id"] == "413"
    assert report["sites"] == ["metabase"]
    assert report["step"] == 2
    assert report["page_url"] == "http://localhost:3000/question/notebook"
    assert "secret" not in json.dumps(report)
    assert "playwright" in report["runtime"]["packages"]
    assert is_fatal_worker_error(type(raised.value).__name__ + ": " + str(raised.value))
    assert not is_fatal_worker_error("Target page, context or browser has been closed")


def test_non_crash_exception_is_preserved(tmp_path):
    error = PlaywrightError("Target page, context or browser has been closed")

    @browser_operation("reset")
    def reset(env):
        raise error

    with pytest.raises(PlaywrightError) as raised:
        reset(_env(tmp_path))
    assert raised.value is error
    assert not (tmp_path / "browser_failure.json").exists()


def test_failed_evidence_write_does_not_mask_crash(tmp_path):
    monitor = BrowserCrashMonitor(_env(tmp_path / "missing"))
    with pytest.raises(WebArenaProBrowserCrashError) as raised:
        monitor.check("reset", PlaywrightError("Page.goto: Page crashed"))
    assert isinstance(raised.value.__cause__, PlaywrightError)


class EventSource:
    def __init__(self, **properties):
        self.__dict__.update(properties)
        self.listeners = {}

    def on(self, event, callback):
        self.listeners.setdefault(event, []).append(callback)

    def emit(self, event, *args):
        for callback in self.listeners.get(event, ()):
            callback(*args)


def _run_fake_coroutine(coroutine):
    # BrowserGym retains its global Playwright loop between live tests. These
    # fake objects have no loop affinity; give their coroutine an isolated loop.
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result(timeout=5)


def _wire_bounded_close(page, context):
    from unittest.mock import AsyncMock, Mock

    async def close():
        context.pages.remove(page)
        page.is_closed.return_value = True

    page.close = Mock(side_effect=AssertionError("Never call unbounded sync Page.close"))
    page.is_closed = Mock(return_value=False)
    page._sync = _run_fake_coroutine
    page._impl_obj = SimpleNamespace(close=AsyncMock(side_effect=close))


def test_close_deadline_cancels_a_pending_close_coroutine(monkeypatch):
    cancelled = []

    async def close():
        try:
            await asyncio.Future()
        finally:
            cancelled.append(True)

    page = SimpleNamespace(_sync=_run_fake_coroutine, _impl_obj=SimpleNamespace(close=close))
    monkeypatch.setattr(
        "webarena_pro_bgym.benchmark.browser_diagnostics._CRASHED_PAGE_CLOSE_TIMEOUT_SECONDS", 0.01,
    )
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        _close_crashed_page(page)
    assert time.monotonic() - started < 1
    assert cancelled == [True]


@pytest.mark.skipif(os.getenv("WEBARENA_PRO_TEST_BROWSER") != "1", reason="opt-in live Chromium")
def test_live_close_deadline_cancels_on_playwright_greenlet_bridge(monkeypatch):
    from browsergym.core import _get_global_playwright

    cancelled = []

    async def pending_close():
        try:
            await asyncio.Future()
        finally:
            cancelled.append(True)

    browser = _get_global_playwright().chromium.launch()
    try:
        context = browser.new_context()
        page = context.new_page()
        with monkeypatch.context() as patch:
            patch.setattr(page._impl_obj, "close", pending_close)
            patch.setattr(
                "webarena_pro_bgym.benchmark.browser_diagnostics._CRASHED_PAGE_CLOSE_TIMEOUT_SECONDS",
                0.01,
            )
            started = time.monotonic()
            with pytest.raises(TimeoutError):
                _close_crashed_page(page)
            assert time.monotonic() - started < 1
            assert cancelled == [True]
        # The timed-out command did not corrupt the connection or abandon
        # the coroutine; ordinary context teardown can still dispose of it.
        context.close()
        assert page.is_closed()
    finally:
        browser.close()


def test_popup_crash_event_cannot_be_swallowed_by_action_or_media_handler(tmp_path):
    env = _env(tmp_path)
    page = EventSource(url=env.page.url)
    popup = EventSource(url="http://localhost:3000/question#encoded")
    env.context = EventSource(pages=[page])
    env.browser = SimpleNamespace(version="123.4")
    env.page = page

    @browser_operation("step")
    def step(env):
        env.context.emit("page", popup)
        popup.emit("crash")
        return "BrowserGym swallowed the action error"

    with pytest.raises(WebArenaProBrowserCrashError) as raised:
        step(env)
    assert raised.value.diagnostics["crash_event_observed"] is True
    assert raised.value.diagnostics["page_url"] == "http://localhost:3000/question"
    assert json.loads((tmp_path / "browser_runtime.json").read_text())["browser_version"] == "123.4"


def test_crash_during_reset_is_classified_before_first_observation(monkeypatch, tmp_path):
    env = WebArenaProEnv.__new__(WebArenaProEnv)
    env.__dict__.update(_env(tmp_path).__dict__)

    def reset(self, seed):
        raise PlaywrightError("Page.goto: Page crashed")

    monkeypatch.setattr(WebArenaProBrowserEnv, "reset", reset)
    with pytest.raises(WebArenaProBrowserCrashError) as raised:
        env.reset()
    assert raised.value.diagnostics["operation"] == "reset"


@pytest.mark.skipif(os.getenv("WEBARENA_PRO_TEST_BROWSER") != "1", reason="opt-in live Chromium")
def test_live_observation_and_forced_renderer_crash(tmp_path, renderer_crash_action):
    from browsergym.core.task import AbstractBrowserTask

    class SmokeTask(AbstractBrowserTask):
        def setup(self, page):
            page.set_content("""<html><body><label>Name <input value='ready'></label>
                <button>Save</button><iframe name='child' srcdoc='<button>Child</button>'></iframe>
                </body></html>""")
            return "Inspect the form", {}

        def validate(self, page, chat_messages, **kwargs):
            return 0, False, "", {}

        def teardown(self):
            pass

    config = SimpleNamespace(task_id="synthetic-renderer-crash", sites=())
    env = WebArenaProEnvArgs(config, "smoke", enable_audio=False).make_env(tmp_path)
    env.task_entrypoint = SmokeTask
    env.task_kwargs = {}
    try:
        observation, _ = env.reset()
        assert observation["axtree_object"]["nodes"]
        for _ in range(10):
            assert env._get_obs()["dom_object"]
        # Chromium intentionally terminates only this renderer. This validates
        # real Playwright events and extraction, not the reported app root cause.
        with pytest.raises(WebArenaProBrowserCrashError) as raised:
            env.step(renderer_crash_action)
        assert raised.value.diagnostics["crash_event_observed"] is True
        assert (tmp_path / "browser_failure.json").exists()
    finally:
        env.close()


@pytest.mark.parametrize("failure", [
    None, "navigation", "disconnected", "replay", "close-timeout", "retained", "create-page", "bridge",
])
def test_recovery_attempts_once_only_with_live_context_and_observed_url(monkeypatch, tmp_path, failure):
    from unittest.mock import Mock
    from webarena_pro_bgym.benchmark.navigation import TaskNavigationGuard

    env = _env(tmp_path)
    original = EventSource(url="http://localhost:3000/question?state=private#query", close=Mock())
    replacement = EventSource(url="about:blank", goto=Mock())
    if failure == "navigation":
        replacement.goto.side_effect = PlaywrightError("Page.goto: Page crashed")
    env.page = original
    env.page_history = {original: None}
    env.context = EventSource(pages=[original], new_page=Mock(return_value=replacement))
    _wire_bounded_close(original, env.context)
    if failure == "close-timeout":
        async def pending_close():
            await asyncio.Future()
        original._impl_obj.close.side_effect = pending_close
        monkeypatch.setattr(
            "webarena_pro_bgym.benchmark.browser_diagnostics._CRASHED_PAGE_CLOSE_TIMEOUT_SECONDS", 0.01,
        )
    elif failure == "retained":
        original._impl_obj.close.side_effect = None
    elif failure == "create-page":
        env.context.new_page.side_effect = PlaywrightError("Cannot create a page")
    elif failure == "bridge":
        del original._sync
    env.browser = SimpleNamespace(version="125", is_connected=lambda: failure != "disconnected")
    env.last_action = "click('save')"
    env._checkpoint_replaying = failure == "replay"
    guard = TaskNavigationGuard(["http://localhost:3000"])
    guard.remember_pages([original])
    env.task = SimpleNamespace(navigation_guard=guard)
    monitor = BrowserCrashMonitor(env)
    monitor.attach()
    original.emit("crash")
    if failure:
        with pytest.raises(WebArenaProBrowserCrashError):
            monitor.check("observation")
        attempted = failure not in {"disconnected", "replay"}
        assert env.context.new_page.call_count == int(attempted)
        if attempted:
            saved = json.loads((tmp_path / "browser_recoveries.json").read_text())
            assert saved[0]["status"] == "failed"
            if failure == "close-timeout":
                assert saved[0]["recovery_error_type"] == "TimeoutError"
        if failure != "navigation":
            replacement.goto.assert_not_called()
    else:
        assert monitor.check("observation") is True
        replacement.goto.assert_called_once_with(
            original.url, timeout=15000, wait_until="domcontentloaded",
        )
        assert env.page is replacement
        assert original not in env.page_history
        assert original not in env.context.pages
        assert "not replayed" in env.last_action_error
        with pytest.raises(WebArenaProBrowserCrashError):
            monitor.check("observation", PlaywrightError("Page.screenshot: Target crashed"))
        env.context.new_page.assert_called_once()
        saved = json.loads((tmp_path / "browser_recoveries.json").read_text())
        assert "private" not in json.dumps(saved)
        assert saved[0]["status"] == "restored"
        assert (tmp_path / "browser_recoveries.json").stat().st_mode & 0o777 == 0o600
    original.close.assert_not_called()


def test_interrupted_recovery_records_terminal_status_without_swallowing_interrupt(tmp_path):
    from unittest.mock import Mock
    from webarena_pro_bgym.benchmark.navigation import TaskNavigationGuard

    class StepDeadline(BaseException):
        pass

    env = _env(tmp_path)
    original = EventSource(url="http://localhost:3000/question")
    env.page = original
    env.page_history = {original: None}
    interrupt = StepDeadline()
    env.context = EventSource(pages=[original], new_page=Mock(side_effect=interrupt))
    env.browser = SimpleNamespace(version="125", is_connected=lambda: True)
    env.last_action = "click('save')"
    guard = TaskNavigationGuard(["http://localhost:3000"])
    guard.remember_pages([original])
    env.task = SimpleNamespace(navigation_guard=guard)
    monitor = BrowserCrashMonitor(env)
    with pytest.raises(StepDeadline) as raised:
        monitor.check("observation", PlaywrightError("Page.evaluate: Target crashed"))
    assert raised.value is interrupt
    saved = json.loads((tmp_path / "browser_recoveries.json").read_text())
    assert saved[0]["status"] == "interrupted"
    assert saved[0]["recovery_error_type"] == "StepDeadline"


def test_successful_reset_renews_recovery_but_fatal_reset_is_refused(monkeypatch, tmp_path):
    from unittest.mock import Mock
    from webarena_pro_bgym.benchmark.navigation import TaskNavigationGuard

    env = WebArenaProEnv.__new__(WebArenaProEnv)
    env.__dict__.update(_env(tmp_path).__dict__)
    resets = []

    def reset(self, seed):
        resets.append(seed)
        page = EventSource(url="http://localhost:3000/question", close=Mock())
        replacement = EventSource(url="about:blank", goto=Mock())
        self.page = page
        self.page_history = {page: None}
        self.context = EventSource(pages=[page], new_page=Mock(return_value=replacement))
        _wire_bounded_close(page, self.context)
        self.browser = SimpleNamespace(version="125", is_connected=lambda: True)
        guard = TaskNavigationGuard(["http://localhost:3000"])
        guard.remember_pages([page])
        self.task = SimpleNamespace(navigation_guard=guard)
        return {}, {}

    monkeypatch.setattr(WebArenaProBrowserEnv, "reset", reset)
    for seed in (1, 2):
        env.reset(seed=seed)
        monitor = env._browser_crash_monitor
        assert monitor.recovery_attempts == 0
        env.last_action = "click('save')"
        assert monitor.check("observation", PlaywrightError("Page.evaluate: Target crashed"))
        assert monitor.recovery_attempts == 1
        env.context.new_page.assert_called_once()
        assert len(monitor.recoveries) == seed

    saved = json.loads((tmp_path / "browser_recoveries.json").read_text())
    assert [report["status"] for report in saved] == ["restored", "restored"]
    with pytest.raises(WebArenaProBrowserCrashError) as failure:
        monitor.check("observation", PlaywrightError("Page.evaluate: Target crashed"))
    with pytest.raises(WebArenaProBrowserCrashError) as reset_failure:
        env.reset(seed=3)
    assert reset_failure.value is failure.value
    assert resets == [1, 2]
    assert monitor.recovery_attempts == 1
