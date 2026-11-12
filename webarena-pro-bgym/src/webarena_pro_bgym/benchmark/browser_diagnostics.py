"""Diagnose renderer failures and permit one observation-only tab recovery."""

import asyncio
from functools import wraps
from importlib import metadata
import json
import logging
import os
from pathlib import Path
import platform
import re
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightError

from .navigation import safe_url

logger = logging.getLogger(__name__)
_CRASHED_PAGE_CLOSE_TIMEOUT_SECONDS = 2.0
_CRASH_MESSAGE = re.compile(
    r"^(?:(?:\w+\.\w+|Protocol error \([^)]*\)):\s*)*(?:target|page) crashed\b",
    re.IGNORECASE,
)


class WebArenaProBrowserCrashError(RuntimeError):
    """Fatal environment failure; the runner must discard this worker runtime."""

    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__("environment_error: renderer_crash " + json.dumps(diagnostics))


def is_renderer_crash(error: BaseException) -> bool:
    """Do not mistake ordinary page closure or JavaScript errors for crashes."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, PlaywrightError) and _CRASH_MESSAGE.search(str(error)):
            return True
        error = error.__cause__ or error.__context__
    return False


def _close_crashed_page(page):
    # Page.close() has no timeout, including with a default Playwright timeout.
    # Use the same event loop/greenlet bridge as the pinned sync API, but bound
    # its underlying coroutine. Do not move Playwright objects to another thread
    # or consume the runner's SIGALRM. Keep this private-API dependency isolated:
    # an incompatible bridge fails recovery and discards the worker safely.
    sync = page._sync
    close = page._impl_obj.close
    sync(asyncio.wait_for(close(), timeout=_CRASHED_PAGE_CLOSE_TIMEOUT_SECONDS))


def _page_url(page):
    # URL is a cached Playwright property. Never evaluate, screenshot or send CDP
    # requests while collecting a failure. Omit credentials and query payloads.
    try:
        url = urlsplit(page.url)
        if url.scheme not in ("http", "https"):
            return url.scheme + ":" if url.scheme else None
        return urlunsplit((url.scheme, url.netloc.rsplit("@", 1)[-1], url.path, "", ""))
    except Exception:
        return None


def browser_runtime(browser=None, launch_options=None):
    versions = {}
    for package in ("playwright", "browsergym-core", "agentlab"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    report = {
        "packages": versions,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "browser_version": getattr(browser, "version", None),
        "launch_options": {
            key: str(value) for key, value in (launch_options or {}).items()
            if key in ("channel", "executable_path", "headless")
        },
    }
    try:
        manifest = metadata.distribution("playwright").locate_file(
            "playwright/driver/package/browsers.json"
        )
        report["bundled_chromium"] = [
            item for item in json.loads(manifest.read_text())["browsers"]
            if item["name"] in ("chromium", "chromium-headless-shell")
        ]
    except (OSError, KeyError, ValueError, metadata.PackageNotFoundError):
        report["bundled_chromium"] = None
    return report


class BrowserCrashMonitor:
    def __init__(self, env):
        self.env = env
        self.pages = set()
        self.context = None
        self.browser = None
        self.runtime = None
        self.crashed_page_url = None
        self.crash_event = False
        self.crashed_page = None
        self.failure = None
        self.recovery_attempts = 0
        self.recoveries = []

    def _write(self, name, report):
        directory = getattr(self.env, "browser_diagnostics_dir", None)
        if directory is None:
            return
        try:
            path = Path(directory) / name
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
                json.dump(report, out, indent=2)
                out.write("\n")
        except OSError:
            # Evidence collection must never replace the original failure.
            logger.warning("Could not save browser diagnostics", exc_info=True)

    def _watch_page(self, page):
        if page in self.pages:
            return
        self.pages.add(page)

        def crashed(*_):
            self.crash_event = True
            self.crashed_page = page
            self.crashed_page_url = _page_url(page)

        page.on("crash", crashed)

    def attach(self):
        context = getattr(self.env, "context", None)
        if context is not None and not callable(getattr(context, "on", None)):
            return
        if context is not None and context is not self.context:
            self.context = context
            context.on("page", self._watch_page)
        if context is not None:
            for page in context.pages:
                self._watch_page(page)
        browser = getattr(self.env, "browser", None)
        if browser is not None and browser is not self.browser:
            self.browser = browser
            options = {"headless": getattr(self.env, "headless", None)}
            options.update(getattr(self.env, "pw_chromium_kwargs", {}))
            self.runtime = browser_runtime(browser, options)
            logger.info("Browser runtime: %s", json.dumps(self.runtime))
            self._write("browser_runtime.json", self.runtime)

    def _recover_page(self, operation):
        # A crashed renderer can be replaced without rerunning an agent action,
        # task setup, login or a backend reset. Never rebuild a disconnected
        # browser/context, or continue a checkpoint replay with different state.
        env = self.env
        guard = getattr(getattr(env, "task", None), "navigation_guard", None)
        page = self.crashed_page or getattr(env, "page", None)
        previous = guard.last_urls.get(page) if guard is not None else None
        if (operation != "observation" or self.recovery_attempts or not previous
                or page is not getattr(env, "page", None)
                or getattr(env, "_checkpoint_replaying", False)
                or not getattr(env, "last_action", "")
                or not env.browser.is_connected()):
            return False
        self.recovery_attempts += 1
        report = {
            "operation": operation, "step": env.steps_taken,
            "page_url": self.crashed_page_url or _page_url(page),
            "restore_url": safe_url(previous),
            "crash_event_observed": self.crash_event,
            "runtime": self.runtime,
            "recovery": "replace_tab_same_context; no action replay",
            "state": "server state, cookies and localStorage retained; unsaved DOM and sessionStorage lost",
            "status": "attempting",
        }
        self.recoveries.append(report)
        self._write("browser_recoveries.json", self.recoveries)
        try:
            replacement = env.context.new_page()
            env.page = replacement
            env.page_history.pop(page, None)
            env.page_history[replacement] = None
            _close_crashed_page(page)
            # BrowserGym observations, tab actions, and page settling enumerate
            # context.pages. A retained crashed tab would poison the next step.
            if not page.is_closed() or page in env.context.pages:
                raise RuntimeError("Crashed tab remained open after bounded close")
            self.crash_event = False
            self.crashed_page = None
            self.crashed_page_url = None
            replacement.goto(previous, timeout=15000, wait_until="domcontentloaded")
            if self.crash_event:
                raise RuntimeError("Replacement renderer crashed")
            env.last_action_error = (
                "The browser renderer crashed. Restored the last observed task URL in a new tab. "
                "The previous action was not replayed and may already have changed the application. "
                "Server state, cookies and localStorage were retained; unsaved page edits and "
                "sessionStorage may be lost. Inspect the current state before continuing."
            )
            report["status"] = "restored"
            logger.warning("Browser recovery: %s", json.dumps(report))
            return True
        except BaseException as recovery_error:
            self.crash_event = self.crash_event or report["crash_event_observed"]
            self.crashed_page_url = self.crashed_page_url or report["page_url"]
            interrupted = not isinstance(recovery_error, Exception)
            report["status"] = "interrupted" if interrupted else "failed"
            report["recovery_error_type"] = type(recovery_error).__name__
            if interrupted:
                raise
            return False
        finally:
            self._write("browser_recoveries.json", self.recoveries)

    def check(self, operation, error=None):
        if self.failure is not None:
            raise self.failure
        if not self.crash_event and not (error is not None and is_renderer_crash(error)):
            return False
        if self._recover_page(operation):
            return True
        config = getattr(getattr(self.env, "env_args", None), "task_config", None)
        report = {
            "error_type": "environment_error",
            "reason": "renderer_crash",
            "operation": operation,
            "task_id": getattr(config, "task_id", None),
            "sites": list(getattr(config, "sites", ())),
            "step": getattr(self.env, "steps_taken", None),
            "page_url": self.crashed_page_url or _page_url(getattr(self.env, "page", None)),
            "crash_event_observed": self.crash_event,
            "runtime": self.runtime or browser_runtime(getattr(self.env, "browser", None)),
            "recovery": "abort_task_discard_worker; no action replay",
            "recovery_attempts": self.recovery_attempts,
        }
        self.failure = WebArenaProBrowserCrashError(report)
        self._write("browser_failure.json", report)
        logger.error("%s", self.failure)
        raise self.failure from error


def browser_operation(operation):
    """Classify errors at boundaries, including errors swallowed by BrowserGym."""
    def decorate(function):
        @wraps(function)
        def wrapped(env, *args, **kwargs):
            monitor = getattr(env, "_browser_crash_monitor", None)
            if monitor is None:
                monitor = env._browser_crash_monitor = BrowserCrashMonitor(env)
            monitor.check(operation)
            # Only observation extraction can repeat. step/reset/budget grading
            # remain single calls even when their nested observation recovers.
            while True:
                try:
                    monitor.attach()
                    result = function(env, *args, **kwargs)
                except WebArenaProBrowserCrashError:
                    raise
                except Exception as error:
                    if monitor.check(operation, error):
                        continue
                    raise
                if monitor.check(operation):
                    continue
                if operation == "reset":
                    # A successful reset starts a new episode. Keep prior
                    # diagnostics, but renew its single recovery allowance.
                    # Fatal monitors are rejected by check() before reset runs.
                    monitor.recovery_attempts = 0
                return result
        return wrapped
    return decorate
