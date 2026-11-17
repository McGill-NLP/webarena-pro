"""Private Core/browser supervisor. Its IPC methods are never model tools.

A separate process owns async Playwright, login, guards, and download listeners.
Core evaluation consumes captured facts on a dedicated thread. A private,
short-lived CDP observer captures the exact selected target for each grade.
"""

from __future__ import annotations

import asyncio
import io
import ipaddress
import json
import multiprocessing
import os
import re
import signal
import socket
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, nullcontext
from datetime import date
from functools import partial
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .browser_identity import BrowserIdentityError, browser_document_kind, identity_capture, resolve_page
from .artifacts import safe_error
from .tool_policy import PolicyError, URLPolicy


@asynccontextmanager
async def evaluation_page(endpoint, identity):
    """Capture through fresh client bookkeeping, never substitute another target.

    The owning Playwright client can report an empty/closed context while the
    same Chromium target is still live through the agent and media clients.
    A fresh observer avoids that stale client state without changing browser
    settings, navigating, or relaxing target/document identity checks.
    """
    from playwright.async_api import async_playwright

    observer = await async_playwright().start()
    try:
        browser = await observer.chromium.connect_over_cdp(endpoint, no_defaults=True)
        if len(browser.contexts) != 1:
            raise BrowserIdentityError("Unexpected browser contexts during private capture")
        yield await resolve_page(browser.contexts[0], identity)
    finally:
        # Disconnect this observer only; never close the agent's browser.
        await observer.stop()


async def wait_for_devtools_endpoint(profile: str | Path, timeout: float = 30) -> str:
    """Wait for Chromium's HTTP debugger, which starts independently of its pipe."""
    port_file = Path(profile) / "DevToolsActivePort"
    try:
        async with asyncio.timeout(timeout):
            while True:
                try:
                    port_line, separator, _ = port_file.read_text().partition("\n")
                    port = int(port_line)
                except (FileNotFoundError, ValueError):
                    pass
                else:
                    # Require a complete port line, not a partially written number.
                    if separator and 0 < port < 65536:
                        return f"http://127.0.0.1:{port}"
                await asyncio.sleep(0.05)
    except TimeoutError as exc:
        raise TimeoutError(
            f"Chromium did not publish a valid DevToolsActivePort within {timeout:g} seconds"
        ) from exc


def browser_origins(urls):
    """Canonical task origins for Chromium's scoped permissions and flags."""
    urls = list(urls)
    for url in urls:
        if any(character.isspace() or ord(character) < 32 for character in url) or "\\" in url:
            raise ValueError("Task origins cannot contain whitespace, controls, or backslashes")
        parsed = urlsplit(url)
        if parsed.port == 0 or (
            parsed.netloc.startswith("[")
            and not re.fullmatch(r"\[[0-9a-fA-F:.]+\](?::[0-9]+)?", parsed.netloc)
        ):
            raise ValueError("Malformed task origin authority")
    origins = []
    for scheme, host, port in sorted(URLPolicy(urls).origins):
        # Chromium interprets this flag separately from Python's URL parser.
        # Accept only literal IPs or DNS names, never wildcards, encoded
        # authorities, separators, or malformed hostnames.
        try:
            ipaddress.ip_address(host)
            valid_host = "%" not in host
        except ValueError:
            valid_host = len(host) <= 253 and all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.rstrip(".").split(".")
            )
        if not valid_host:
            raise ValueError("Task origins require a literal IP address or DNS hostname")
        host = f"[{host}]" if ":" in host else host
        origins.append(f"{scheme}://{host}:{port}")
    return origins


def private_paths(sites: tuple[str, ...]) -> list[str]:
    from webarena_pro_core.eval.api_registry import SITE_API_REGISTRY
    from webarena_pro_core.state_reset import reset_endpoints_for_site

    paths = []
    for site in sites:
        paths.extend(path for _, path in reset_endpoints_for_site(site))
        for spec in SITE_API_REGISTRY.get(site, {}).values():
            if spec.get("auth_mode") == "eval_token":
                path = re.sub(r"^__[\w-]+__", "", spec["url"]).split("?", 1)[0]
                paths.append(path.split("{", 1)[0].rstrip("/"))
    return paths


class BrowserGuard:
    def __init__(self, policy: URLPolicy):
        self.policy = policy
        self.violations: list[str] = []
        self.sessions = []
        self.guarded_pages = set()

    def check_response(self, url, headers, *, navigation):
        location = headers.get("location")
        if location:
            self.policy.check(urljoin(url, location), navigation=navigation)
        if navigation and headers.get("content-type", "").split(";", 1)[0].lower() in {
            "application/json",
            "text/json",
        }:
            raise PolicyError("Direct API response navigation blocked")

    async def attach(self, context, page):
        # Playwright's route callback handles only the first request in a
        # redirect chain. A response-stage CDP guard validates *every* Location
        # before Chromium follows it, including later redirect hops.
        session = await context.new_cdp_session(page)
        self.sessions.append(session)

        async def paused(event):
            request_id = event["requestId"]
            try:
                self.policy.check(event["request"]["url"], navigation=event.get("resourceType") == "Document")
                headers = {h["name"].lower(): h["value"] for h in event.get("responseHeaders", [])}
                self.check_response(
                    event["request"]["url"], headers, navigation=event.get("resourceType") == "Document"
                )
            except PolicyError as exc:
                self.violations.append(str(exc))
                await session.send("Fetch.failRequest", {"requestId": request_id, "errorReason": "BlockedByClient"})
            else:
                await session.send("Fetch.continueRequest", {"requestId": request_id})

        session.on("Fetch.requestPaused", paused)
        await session.send("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Response"}]})
        self.guarded_pages.add(page)

    async def route(self, route):
        request = route.request
        try:
            self.policy.check(request.url, navigation=request.is_navigation_request())
        except PolicyError as exc:
            self.violations.append(str(exc))
            await route.abort("blockedbyclient")
            return
        try:
            # Validate even a popup's first response before its page listener
            # has installed the CDP response guard.
            response = await route.fetch(max_redirects=0, timeout=30000)
            if response.headers.get("location"):
                try:
                    page_is_guarded = request.frame.page in self.guarded_pages
                except Exception:
                    page_is_guarded = False
                if not page_is_guarded:
                    raise PolicyError(
                        "Popup redirect blocked before its browser guard is ready; navigate using a guarded tab"
                    )
            self.check_response(request.url, response.headers, navigation=request.is_navigation_request())
            await route.fulfill(response=response)
        except PolicyError as exc:
            self.violations.append(str(exc))
            await route.abort("blockedbyclient")
        except Exception:
            try:
                await route.abort("failed")
            except Exception:
                pass

    async def websocket(self, route):
        url = re.sub(r"^ws", "http", route.url)
        try:
            self.policy.check(url)
        except PolicyError as exc:
            self.violations.append(str(exc))
            await route.close()
        else:
            route.connect_to_server()


class Environment:
    """One process-local Core namespace; never stop caller-owned deployments."""

    def __init__(self, sites, namespace, existing, *, external_urls=None):
        self.sites, self.namespace, self.existing = sites, namespace, existing
        self.external_urls = external_urls
        self.owned: list[str] = []

    def setup(self):
        from webarena_pro_core import (
            WEBSITES_ADDITIONAL_HOST_PORT_ENV_VARS,
            build_website_url,
            container_name_for_site,
            site_env_var_key,
            uses_subdomain_urls,
            website_published_ports,
        )
        from webarena_pro_core.website_metadata import (
            deployed_website_login_urls,
            deployed_website_urls,
        )
        from webarena_pro_core.runtime_locks import runtime_lock
        from webarena_pro_core.state_reset import reset_site, wait_until_site_ready
        from webarena_pro_core.task import (
            DEPLOYED_WEBSITE_LOGIN_URLS,
            DEPLOYED_WEBSITE_URLS,
        )

        if self.external_urls is not None:
            # Harbor owns fresh website containers and their teardown. Only
            # configure this process's URLs and wait for the sidecars here.
            if set(self.external_urls) != set(self.sites):
                raise ValueError("External URLs must cover exactly the task websites")
            urls = dict(self.external_urls)
            for site, url in urls.items():
                os.environ[f"WP_{site_env_var_key(site)}_URL"] = url
            DEPLOYED_WEBSITE_URLS.update(urls)
            DEPLOYED_WEBSITE_LOGIN_URLS.update(deployed_website_login_urls(self.sites))
            for site in self.sites:
                wait_until_site_ready(site, wait_for_snapshot=False)
            return urls

        media_ports = {}
        if not self.existing:
            if not uses_subdomain_urls():
                raise ValueError(
                    "Managed MCP runs require subdomain URL mode; use --existing-environment for port deployments"
                )
            os.environ["WP_EXP_HASH"] = self.namespace
            for site in self.sites:
                key = site_env_var_key(site)
                for suffix in ("URL", "CONTAINER_NAME", "EXP_HASH", "HOST_PORT"):
                    if f"WP_{key}_{suffix}" in os.environ:
                        raise ValueError("Explicit site overrides require --existing-environment")
                extra_vars = WEBSITES_ADDITIONAL_HOST_PORT_ENV_VARS.get(site, {})
                if any(variable in os.environ for variable in extra_vars.values()):
                    raise ValueError("Explicit site port overrides require --existing-environment")
                published = website_published_ports(site, use_proxy=True) or {}
                media_ports[site] = {extra_vars[port] for port in published if port in extra_vars}
                os.environ[f"WP_{key}_EXP_HASH"] = self.namespace
                os.environ[f"WP_{key}_URL"] = build_website_url(site, exp_hash=self.namespace)
                os.environ[f"WP_{key}_CONTAINER_NAME"] = container_name_for_site(
                    site, exp_hash=self.namespace
                )
        urls = deployed_website_urls(self.sites)
        # Keep legacy task metadata aligned with the process-local deployment.
        # Current providers resolve their URLs dynamically from environment settings.
        DEPLOYED_WEBSITE_URLS.update(urls)
        DEPLOYED_WEBSITE_LOGIN_URLS.update(deployed_website_login_urls(self.sites))
        for site in self.sites:
            if not self.existing:
                self.owned.append(site)  # Also clean up a partially created site.
            # Hold the shared lock from port selection through Docker binding.
            # Closing the probe socket alone cannot reserve a port for a worker.
            variables = media_ports.get(site, ())
            with runtime_lock("mcp-additional-ports") if variables else nullcontext():
                for variable in variables:
                    os.environ[variable] = str(free_media_port())
                reset_site(site, backend="auto")
            wait_until_site_ready(site)
        return urls

    def images(self):
        import docker
        from webarena_pro_core import container_name_for_site

        result = {}
        client = None
        try:
            client = docker.from_env(timeout=10)
            for site in self.sites:
                try:
                    container = client.containers.get(container_name_for_site(site))
                    result[site] = {
                        "image_id": container.image.id,
                        "repo_digests": container.image.attrs.get("RepoDigests", []),
                    }
                except Exception:
                    result[site] = {"status": "unavailable"}
        except Exception:
            result = {site: {"status": "unavailable"} for site in self.sites}
        finally:
            if client:
                client.close()
        return result

    def close(self):
        from webarena_pro_core.state_reset import stop_site_container

        errors = []
        for site in reversed(self.owned):
            try:
                stop_site_container(site)
            except Exception:
                errors.append(site)
        if errors:
            raise RuntimeError("Failed to clean up owned sites: " + ", ".join(errors))


def free_media_port() -> int:
    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
            tcp.bind(("0.0.0.0", 0))
            port = tcp.getsockname()[1]
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                try:
                    udp.bind(("0.0.0.0", port))
                except OSError:
                    continue
                return port
    raise RuntimeError("Cannot allocate a free TCP/UDP media port")


async def authenticate(task, page, urls):
    from webarena_pro_core.autologin.async_api import AutoLogin
    from webarena_pro_core.website_metadata import deployed_website_login_urls

    if task.require_login:
        login = AutoLogin(urls=urls, login_urls=deployed_website_login_urls(task.sites))
        for site in task.sites:
            await login.ui_login(site=site, page=page, username=(task.login_usernames or {}).get(site))


def _serve(*args):
    asyncio.run(_serve_async(*args))


async def _serve_async(
    connection, task, directory, namespace, existing, fixture_urls, headed, task_start,
    external_urls=None,
):
    from playwright.async_api import async_playwright

    from webarena_pro_core.eval.ui_evidence import build_ui_evidence_plan
    from webarena_pro_core.ui_evidence.async_api import collect_ui_evidence

    from .evaluation import CoreEvaluator

    os.umask(0o077)

    # Cancellation unwinds browser/site cleanup; the parent still enforces a
    # bounded terminate/kill deadline if a blocking Core operation hangs.
    loop = asyncio.get_running_loop()
    owner = asyncio.current_task()
    loop.add_signal_handler(signal.SIGTERM, owner.cancel)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="core-evaluation")

    async def private_call(function, *args, **kwargs):
        pending = loop.run_in_executor(executor, partial(function, *args, **kwargs))
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            # Do not tear down a browser or reset sites under an active grader.
            try:
                await pending
            finally:
                raise

    environment = Environment(task.sites, namespace, existing, external_urls=external_urls)
    context = None
    runtime = None
    evaluator = None
    callbacks = set()
    callback_errors = []
    download_sequence = 0

    def schedule(coroutine):
        pending = asyncio.create_task(coroutine)
        callbacks.add(pending)

        def completed(result):
            callbacks.discard(result)
            if not result.cancelled() and result.exception():
                callback_errors.append(type(result.exception()).__name__)

        pending.add_done_callback(completed)

    async def flush_callbacks():
        while callbacks:
            await asyncio.gather(*list(callbacks), return_exceptions=True)
        if callback_errors:
            raise RuntimeError("Browser listener failed: " + ", ".join(callback_errors))

    downloads: list[dict] = []
    download_errors: list[str] = []
    temp = tempfile.TemporaryDirectory(prefix="webarena-mcp-profile-")
    try:
        start_date, start_time = (
            (date.fromisoformat(task_start["date"]), task_start["time_ms"])
            if task_start
            else (date.today(), time.time_ns() // 1_000_000)
        )
        urls = fixture_urls if fixture_urls is not None else await private_call(environment.setup)
        if task.startup_wait_seconds:
            await asyncio.sleep(task.startup_wait_seconds)
        task_origins = browser_origins(urls.values())
        insecure_origins = [url for url in task_origins if url.startswith("http:")]
        browser_args = ["--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0"]
        if insecure_origins:
            # Benchmark sites are private HTTP deployments (e.g. Harbor's
            # http://penpot:9001). Their Clipboard API still needs a secure
            # context; never grant that exception to arbitrary origins.
            browser_args.append("--unsafely-treat-insecure-origin-as-secure=" + ",".join(insecure_origins))
        runtime = await async_playwright().start()
        context = await runtime.chromium.launch_persistent_context(
            temp.name,
            # The headless shell ignores secure-origin exceptions. Use the
            # pinned full Chromium build in its supported new headless mode.
            channel="chromium",
            headless=not headed,
            accept_downloads=True,
            viewport={"width": 1280, "height": 720},
            service_workers="block",
            args=browser_args,
            env={
                key: os.environ[key]
                for key in ("PATH", "HOME", "TMPDIR", "DISPLAY", "XAUTHORITY", "SYSTEMROOT")
                if key in os.environ
            },
        )
        for task_origin in task_origins:
            await context.grant_permissions(["clipboard-read", "clipboard-write"], origin=task_origin)
        context.set_default_timeout(15000)
        page = context.pages[0]
        blocked = private_paths(task.sites)
        guard = BrowserGuard(URLPolicy(list(urls.values()), blocked))
        await context.route("**/*", guard.route)
        await context.route_web_socket("**/*", guard.websocket)

        async def capture(download):
            nonlocal download_sequence
            sequence = download_sequence
            download_sequence += 1
            try:
                destination = (
                    Path(directory)
                    / "downloads"
                    / f"{sequence:04d}-{Path(download.suggested_filename).name}"
                )
                destination.parent.mkdir(exist_ok=True, mode=0o700)
                await download.save_as(destination)
                downloads.append(
                    {
                        "path": str(destination),
                        "suggested_filename": download.suggested_filename,
                        "url": download.url,
                    }
                )
            except Exception as exc:
                download_errors.append(type(exc).__name__)

        async def attach(opened):
            opened.on("download", lambda download: schedule(capture(download)))
            await guard.attach(context, opened)

        context.on("page", lambda opened: schedule(attach(opened)))
        await attach(page)
        await authenticate(task, page, urls)
        endpoint = await wait_for_devtools_endpoint(temp.name)
        evaluator = CoreEvaluator(task, start_date, start_time)
        plan = build_ui_evidence_plan(task.evaluation or {})
        baselines = await private_call(evaluator.capture_baselines)
        (Path(directory) / "baselines.json").write_text(
            json.dumps(
                baselines,
                indent=2,
            )
        )
        await flush_callbacks()
        connection.send(
            {
                "ok": True,
                "value": {
                    "endpoint": endpoint,
                    "urls": urls,
                    "blocked_paths": blocked,
                    "browser_version": context.browser.version,
                    "images": await private_call(environment.images)
                    if fixture_urls is None and external_urls is None else {},
                    "task_start_date": start_date.isoformat(),
                    "task_start_time_ms": start_time,
                },
            }
        )
        while True:
            if not connection.poll():
                await asyncio.sleep(0.02)
                continue
            method, params = connection.recv()
            if method == "close":
                break
            try:
                await flush_callbacks()
                if method == "evaluate":
                    identity = params.pop("identity")
                    async with evaluation_page(endpoint, identity) as active:
                        if not browser_document_kind(identity["url"]):
                            guard.policy.check(identity["url"], navigation=True)
                        if download_errors:
                            raise RuntimeError("Download evidence capture failed")
                        import numpy as np
                        from PIL import Image

                        step = params["trajectory"][-1]["step"] if params["trajectory"] else 0
                        screenshot_path = Path(directory) / f"evaluation-{step}.png"
                        async with identity_capture(active, identity):
                            observation = {
                                "url": identity["url"],
                                "axtree_txt": params.pop("snapshot"),
                                "screenshot": np.array(
                                    Image.open(io.BytesIO(await active.screenshot(path=screenshot_path))).convert("RGB")
                                ),
                            }
                            await flush_callbacks()
                            if download_errors:
                                raise RuntimeError("Download evidence capture failed")
                            evidence = await collect_ui_evidence(active, plan, step=step)
                    if evidence.status == "stale":
                        raise BrowserIdentityError("Browser identity changed during evidence capture")
                    value = await private_call(
                        evaluator.evaluate, ui_evidence=evidence.model_dump(mode="json"),
                        evaluation_id=evidence.evaluation_id, evaluation_step=step,
                        evaluation_tab_id=evidence.tab_id,
                        observation=observation, downloads=list(downloads), **params
                    )
                    value["screenshot_file"] = str(screenshot_path)
                elif method == "diagnostics":
                    value = {
                        "downloads": downloads,
                        "download_errors": download_errors,
                        "blocked_requests": guard.violations,
                    }
                    guard.violations = []
                else:
                    raise ValueError("Unknown supervisor method")
                connection.send({"ok": True, "value": value})
            except Exception as exc:
                connection.send({"ok": False, "error": safe_error(exc),
                                 "error_code": "browser_identity_changed"
                                 if isinstance(exc, BrowserIdentityError) else None})
    except Exception as exc:
        try:
            connection.send({"ok": False, "error": safe_error(exc),
                                 "error_code": "browser_identity_changed"
                                 if isinstance(exc, BrowserIdentityError) else None})
        except (BrokenPipeError, OSError):
            pass
    finally:
        cleanup_errors = []
        for operation in (
            flush_callbacks,
            lambda: context.close() if context else asyncio.sleep(0),
            lambda: runtime.stop() if runtime else asyncio.sleep(0),
            lambda: private_call(environment.close),
            lambda: private_call(temp.cleanup),
        ):
            try:
                await operation()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        executor.shutdown(wait=False)
        loop.remove_signal_handler(signal.SIGTERM)
        try:
            connection.send(
                {
                    "ok": not cleanup_errors,
                    "value": None,
                    "error": "Cleanup failed: " + ", ".join(cleanup_errors),
                }
            )
        except (BrokenPipeError, OSError):
            pass
        connection.close()


class Supervisor:
    def __init__(
        self,
        task,
        directory: Path,
        namespace: str,
        *,
        existing=False,
        fixture_urls=None,
        headed=False,
        task_start=None,
        external_urls=None,
    ):
        ctx = multiprocessing.get_context("spawn")
        self.connection, child = ctx.Pipe()
        self.process = ctx.Process(
            target=_serve,
            args=(child, task, str(directory), namespace, existing, fixture_urls, headed, task_start, external_urls),
        )
        self.child = child
        self.broken = False

    async def receive(self, timeout):
        try:
            ready = await asyncio.to_thread(self.connection.poll, timeout)
        except asyncio.CancelledError:
            # An outstanding response cannot be consumed by another request.
            # Cleanup terminates the worker instead of reusing this channel.
            self.broken = True
            raise
        if not ready:
            self.broken = True
            raise TimeoutError("Core/browser supervisor timed out")
        result = self.connection.recv()
        if not result["ok"]:
            if result.get("error_code") == "browser_identity_changed":
                raise BrowserIdentityError(result["error"])
            raise RuntimeError(result["error"])
        return result["value"]

    async def start(self, timeout=1800):
        self.process.start()
        self.child.close()
        return await self.receive(timeout)

    async def call(self, method, *, timeout=120, **params):
        if self.broken:
            raise RuntimeError("Supervisor is no longer synchronized")
        self.connection.send((method, params))
        return await self.receive(timeout)

    async def close(self):
        try:
            if self.process.is_alive():
                if not self.broken:
                    self.connection.send(("close", {}))
                    await self.receive(30)
                else:
                    self.process.terminate()
                await asyncio.to_thread(self.process.join, 30)
        finally:
            if self.process.is_alive():
                self.process.terminate()
                await asyncio.to_thread(self.process.join, 10)
            if self.process.is_alive():
                self.process.kill()
                await asyncio.to_thread(self.process.join, 5)
            self.connection.close()
            self.child.close()
