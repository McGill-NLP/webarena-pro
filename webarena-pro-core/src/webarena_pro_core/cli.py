"""WebArena-Pro CLI. This module provides command-line interface for managing WebArena-Pro environments and containers.

usage:
    webarena-pro env list
    webarena-pro env pull <env_name|all>
    webarena-pro env start <env_name...|all> [--login|--auto_login] [--wait-timeout SECONDS]
    webarena-pro env stop <env_name...|all>
    webarena-pro env restart <env_name|all>
    webarena-pro env status <env_name>
    webarena-pro env dashboard [--host <host>] [--port <port>]
    webarena-pro run --site <site> [eval args...]
    webarena-pro run dashboard [dashboard args...]
    webarena-pro serve [--host <host>] [--port <port>]
    webarena-pro help
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from pathlib import Path
from typing import Callable, Iterable

import docker

from . import (
    WEBSITES_CONTAINER_PORTS,
    WEBSITES_HOST_PORTS,
    WEBSITES_IMAGES,
    active_exp_hash,
    build_website_url,
    website_published_ports,
    container_name_for_site,
    labels_for_site,
    uses_subdomain_urls,
    website_environment,
)
from .docker import DockerContainerManager
from .docker import configured_docker_platform
from .nginx import NginxProxyManager, docker_network_name
from .state_reset import (
    post_start_site_setup,
    site_container_run_overrides,
    site_volume_overrides,
)

DEFAULT_AUTH_DIR = ".auth"
DEFAULT_LOGIN_BROWSER = "chromium"
DEFAULT_LOGIN_WAIT_SECONDS = 120.0
DEFAULT_START_WAIT_SECONDS = DEFAULT_LOGIN_WAIT_SECONDS
DEFAULT_LOGIN_MAX_ATTEMPTS = 3
LOCAL_NATIVE_BUILD_SITES = {"thunderbird"}
WEBSITE_READINESS_PATHS = {
    "erp-next": "/api/method/ping",
    "penpot": "/api/rpc/command/get-profile",
    "immich": "/api/server/ping",
    "mattermost": "/api/v4/system/ping",
    "metabase": "/api/health",
    "nextcloud": "/status.php",
}


class _Ansi:
    RESET = "0"
    BOLD = "1"
    DIM = "2"
    UNDERLINE = "4"
    RED = "31"
    GREEN = "32"
    YELLOW = "33"
    BLUE = "34"
    MAGENTA = "35"
    CYAN = "36"
    GRAY = "90"


def _env_flag_enabled(name: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return False
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


def _color_enabled(stream: object | None = None) -> bool:
    if os.environ.get("NO_COLOR") is not None or _env_flag_enabled("WEBARENA_PRO_NO_COLOR"):
        return False
    if _env_flag_enabled("FORCE_COLOR") or _env_flag_enabled("WEBARENA_PRO_FORCE_COLOR"):
        return True
    if os.environ.get("TERM") == "dumb":
        return False
    stream = sys.stdout if stream is None else stream
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def _paint(text: object, *codes: str, stream: object | None = None) -> str:
    value = str(text)
    if not codes or not _color_enabled(stream=stream):
        return value
    return f"\033[{';'.join(codes)}m{value}\033[{_Ansi.RESET}m"


def _heading(text: str) -> str:
    return _paint(text, _Ansi.BOLD, _Ansi.CYAN)


def _muted(text: object) -> str:
    return _paint(text, _Ansi.DIM, _Ansi.GRAY)


def _label(text: str) -> str:
    return _paint(text, _Ansi.BOLD, _Ansi.GRAY)


def _value(text: object) -> str:
    return _paint(text, _Ansi.BOLD)


def _site(text: object) -> str:
    return _paint(text, _Ansi.BOLD, _Ansi.CYAN)


def _image(text: object) -> str:
    return _paint(text, _Ansi.MAGENTA)


def _path(text: object) -> str:
    return _paint(text, _Ansi.MAGENTA)


def _url(text: object) -> str:
    return _paint(text, _Ansi.UNDERLINE, _Ansi.BLUE)


def _success(text: object) -> str:
    return _paint(text, _Ansi.BOLD, _Ansi.GREEN)


def _warning(text: object) -> str:
    return _paint(text, _Ansi.BOLD, _Ansi.YELLOW)


def _error(text: object) -> str:
    return _paint(text, _Ansi.BOLD, _Ansi.RED)


def _progress(text: object) -> str:
    return _paint(text, _Ansi.BOLD, _Ansi.BLUE)


def _site_prefix(site: str) -> str:
    return _paint(f"[{site}]", _Ansi.BOLD, _Ansi.CYAN)


def _style_message(message: object, *, kind: str) -> str:
    if kind == "success":
        return _success(message)
    if kind == "warning":
        return _warning(message)
    if kind == "error":
        return _error(message)
    if kind == "progress":
        return _progress(message)
    if kind == "log":
        return _muted(message)
    return str(message)


def _print_site(site: str, message: object, *, kind: str = "info", flush: bool = False) -> None:
    print(f"{_site_prefix(site)} {_style_message(message, kind=kind)}", flush=flush)


def _format_status(status: object) -> str:
    value = str(status or "unknown")
    normalized = value.lower()
    if normalized in {"running", "healthy", "up"}:
        return _success(value)
    if normalized in {"created", "starting", "restarting", "paused", "unknown"}:
        return _warning(value)
    if normalized in {"exited", "dead", "unhealthy", "not found", "missing"}:
        return _error(value)
    return _value(value)


def _format_health(health: object) -> str:
    value = str(health or "unknown")
    normalized = value.lower()
    if normalized == "healthy":
        return _success(value)
    if normalized in {"starting", "unknown", "none"}:
        return _warning(value)
    if normalized == "unhealthy":
        return _error(value)
    return _value(value)


def _colorize_help(help_text: str) -> str:
    if not _color_enabled():
        return help_text

    lines: list[str] = []
    for line in help_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("usage:"):
            lines.append(line.replace("usage:", _heading("usage:"), 1))
        elif stripped.endswith(":") and line == stripped:
            lines.append(_heading(line))
        else:
            lines.append(line)
    return "\n".join(lines) + ("\n" if help_text.endswith("\n") else "")


class _ColorArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        return _colorize_help(super().format_help())

    def format_usage(self) -> str:
        return _colorize_help(super().format_usage())


def _add_common_name_argument(parser: argparse.ArgumentParser, *, help: str) -> None:
    parser.add_argument(
        "name",
        metavar="NAME",
        help=help,
    )


def _iter_known_envs() -> Iterable[tuple[str, str]]:
    """Yield (name, image) pairs for all known environments."""
    for name, image in WEBSITES_IMAGES.items():
        yield str(name), str(image)


def _normalize_target_names(names: str | Iterable[str]) -> list[str]:
    raw_names = [names] if isinstance(names, str) else list(names)
    normalized = [str(name).strip() for name in raw_names if str(name).strip()]
    if "all" in normalized:
        if len(normalized) > 1:
            raise SystemExit("Use either 'all' or explicit environment names, not both.")
        return ["all"]

    deduplicated: list[str] = []
    for name in normalized:
        if name not in deduplicated:
            deduplicated.append(name)
    return deduplicated


def _targets_all(names: str | Iterable[str]) -> bool:
    return _normalize_target_names(names) == ["all"]


def _iter_target_envs(names: str | Iterable[str]) -> list[tuple[str, str]]:
    target_names = _normalize_target_names(names)
    if target_names == ["all"]:
        return list(_iter_known_envs())
    return [(name, _resolve_image(name)) for name in target_names]


def _resolve_image(name: str) -> str:
    try:
        return WEBSITES_IMAGES[name]
    except KeyError as error:
        known = ", ".join(sorted(WEBSITES_IMAGES)) or "<none>"
        msg = f"Unknown environment '{name}'. Known environments: {known}"
        raise SystemExit(msg) from error


def _resolve_container_port(name: str) -> int:
    return int(WEBSITES_CONTAINER_PORTS.get(name, 80))


def _resolve_host_port(name: str) -> int:
    try:
        return int(WEBSITES_HOST_PORTS[name])
    except KeyError as error:
        known = ", ".join(sorted(WEBSITES_HOST_PORTS)) or "<none>"
        msg = f"No fixed host port configured for '{name}'. Configured environments: {known}"
        raise SystemExit(msg) from error


def _build_ports(name: str) -> dict[str, int] | None:
    return website_published_ports(
        name, host_port=_resolve_host_port(name), use_proxy=uses_subdomain_urls()
    )


def _network_name() -> str | None:
    return docker_network_name() if uses_subdomain_urls() else None


def _public_url(name: str) -> str:
    return build_website_url(name, host_port=_resolve_host_port(name))


def _host_architecture() -> str:
    machine = platform.machine().lower()
    if machine == "aarch64":
        return "arm64"
    return machine


def _find_local_website_context(site: str) -> Path | None:
    candidates: list[Path] = []
    search_roots = [Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents]
    seen_roots: set[Path] = set()
    for root in search_roots:
        root = root.resolve()
        if root in seen_roots:
            continue
        seen_roots.add(root)
        candidates.append(root / "websites" / site)

    for candidate in candidates:
        if (candidate / "Dockerfile").exists():
            return candidate
    return None


def _ensure_local_native_image_if_needed(
    name: str,
    image: str,
    manager: DockerContainerManager,
) -> None:
    if name not in LOCAL_NATIVE_BUILD_SITES:
        return
    if configured_docker_platform() is not None:
        return

    host_architecture = _host_architecture()
    if host_architecture not in {"arm64", "aarch64"}:
        return

    image_architecture = manager.image_architecture(image)
    if image_architecture == "arm64":
        return

    context = _find_local_website_context(name)
    if context is None:
        return

    manager.build_image(
        path=str(context),
        tag=image,
        log=lambda msg, _name=name: _print_site(_name, msg, kind="log", flush=True),
    )


def _join_url_path(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}" if path else base_url


def _readiness_url(site: str, base_url: str) -> str:
    return _join_url_path(base_url, WEBSITE_READINESS_PATHS.get(site, ""))


def _readiness_response_ok(site: str, status_code: int, body: bytes) -> bool:
    if site == "penpot":
        return status_code == 200 and b'"~:id"' in body

    if site == "erp-next":
        if status_code != 200:
            return False
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return isinstance(data, dict) and data.get("message") == "pong"

    if site == "immich":
        if status_code != 200:
            return False
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return data.get("res") == "pong"

    if site == "mattermost":
        if status_code != 200:
            return False
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return data.get("status") == "OK"

    if site == "metabase":
        return status_code == 200

    if site == "nextcloud":
        if status_code != 200:
            return False
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return data.get("installed") is True

    return status_code < 500


def _wait_until_http_ready(
    site: str,
    url: str,
    *,
    timeout_seconds: float = DEFAULT_LOGIN_WAIT_SECONDS,
    interval_seconds: float = 0.25,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    probe_url = _readiness_url(site, url)
    while time.monotonic() <= deadline:
        try:
            request = Request(probe_url, headers={"User-Agent": "webarena-pro-cli/readiness"})
            with urlopen(request, timeout=5) as response:
                status_code = int(getattr(response, "status", 200))
                body = response.read() if site in WEBSITE_READINESS_PATHS else b""
                if _readiness_response_ok(site, status_code, body):
                    return
        except HTTPError as error:
            if site not in WEBSITE_READINESS_PATHS and error.code < 500:
                return
            last_error = error
        except (OSError, URLError) as error:
            last_error = error
        time.sleep(interval_seconds)

    details = f": {last_error}" if last_error else ""
    raise RuntimeError(f"Timed out waiting for '{site}' at {probe_url}{details}")


def _wait_for_ready_sites(
    site_urls: dict[str, str],
    *,
    timeout_seconds: float = DEFAULT_START_WAIT_SECONDS,
) -> None:
    failures: list[tuple[str, str]] = []
    for site, url in site_urls.items():
        started_at = time.monotonic()
        try:
            _print_site(
                site,
                f"Waiting for website readiness at {_url(_readiness_url(site, url))} ...",
                kind="progress",
                flush=True,
            )
            _wait_until_http_ready(site, url, timeout_seconds=timeout_seconds)
        except Exception as error:
            failures.append((site, str(error)))
            _print_site(site, f"Website readiness failed: {error}", kind="error", flush=True)
            continue

        elapsed = time.monotonic() - started_at
        _print_site(site, f"Website is ready in {elapsed:.1f}s", kind="success", flush=True)

    if failures:
        summary = ", ".join(site for site, _ in failures)
        raise RuntimeError(f"Website readiness failed for: {summary}")


def _auto_login_started_sites(
    site_urls: dict[str, str],
    *,
    auth_dir: Path,
    browser_name: str = DEFAULT_LOGIN_BROWSER,
    headless: bool = True,
    max_attempts: int = DEFAULT_LOGIN_MAX_ATTEMPTS,
) -> None:
    try:
        import playwright.sync_api

        from webarena_pro_core.website_metadata import WEBSITE_LOGIN_PATHS
        from webarena_pro_core.autologin.sync_api import AutoLogin
    except ImportError as error:
        raise SystemExit(
            "Auto-login requires Playwright, a Core dependency. Install "
            "`webarena-pro-core` and run `playwright install chromium`."
        ) from error

    login_urls = {
        site: _join_url_path(url, WEBSITE_LOGIN_PATHS[site])
        for site, url in site_urls.items()
        if site in WEBSITE_LOGIN_PATHS and WEBSITE_LOGIN_PATHS[site] is not None
    }
    auto_login = AutoLogin(urls=site_urls, login_urls=login_urls)
    auth_dir.mkdir(parents=True, exist_ok=True)

    failures: list[tuple[str, str]] = []
    for site, url in site_urls.items():
        output_path = auth_dir / f"{site}_state.json"
        try:
            _print_site(
                site,
                f"Waiting for {_url(url)} before auto-login ...",
                kind="progress",
                flush=True,
            )
            _wait_until_http_ready(site, url)
            _print_site(
                site,
                f"Auto-login {_muted('->')} {_path(output_path)}",
                kind="progress",
                flush=True,
            )
            auto_login.save_storage_state(
                site,
                output_path,
                browser_name=browser_name,
                headless=headless,
                max_attempts=max_attempts,
            )
            _print_site(site, "Auto-login verified.", kind="success", flush=True)
        except Exception as error:
            failures.append((site, str(error)))
            _print_site(site, f"Auto-login failed: {error}", kind="error", flush=True)

    if failures:
        summary = ", ".join(site for site, _ in failures)
        raise RuntimeError(f"Auto-login failed for: {summary}")


def _reload_proxy_if_needed(
    proxy: NginxProxyManager | None,
    *,
    log: Callable[[str], None] | None = None,
) -> None:
    if proxy is not None:
        proxy.ensure_proxy(log=log)


def _preferred_ports(name: str) -> list[str]:
    ports = [str(_resolve_container_port(name)), "80"]
    deduplicated: list[str] = []
    for port in ports:
        if port not in deduplicated:
            deduplicated.append(port)
    return deduplicated


def cmd_list(_: argparse.Namespace) -> int:
    print(_heading("Available WebArena-Pro environments"))
    envs = list(_iter_known_envs())
    if not envs:
        print(f"  {_muted('(none configured)')}")
        return 0

    name_width = max(len(name) for name, _ in envs)
    for name, image in envs:
        container_port = _resolve_container_port(name)
        host_port = _resolve_host_port(name)
        print(f"  {_site(name.ljust(name_width))}  {_image(image)}")
        print(
            "  "
            f"{' ' * name_width}  "
            f"{_label('ports')} {_value(container_port)} {_muted('container')} "
            f"{_muted('->')} {_value(host_port)} {_muted('host')}  "
            f"{_label('url')} {_url(_public_url(name))}"
        )
    return 0


def cmd_pull(args: argparse.Namespace) -> int:
    manager = DockerContainerManager()
    if args.name == "all":
        to_pull = list(_iter_known_envs())
    else:
        image = _resolve_image(args.name)
        to_pull = [(args.name, image)]

    if not to_pull:
        print(_warning("Nothing to pull."))
        return 0

    print(_heading("Pulling WebArena-Pro images"))
    failures = []
    for name, image in to_pull:
        try:
            result = manager.pull_image(
                image,
                log=lambda msg, _name=name: _print_site(_name, msg, kind="log", flush=True),
            )
        except Exception as error:
            failures.append(name)
            _print_site(name, f"Failed to pull {_image(image)}: {error}", kind="error", flush=True)
            continue
        status = {
            "pulled": "Pulled",
            "updated": "Updated",
            "already-current": "Already current",
        }[result.status]
        _print_site(name, f"{status}: {_image(image)}", kind="success", flush=True)

    return 1 if failures else 0


def cmd_start(args: argparse.Namespace) -> int:
    if getattr(args, "auto_login", False) and not _targets_all(args.name):
        raise SystemExit(
            "--auto_login is for `webarena-pro env start all`; "
            "use --login for explicit website names."
        )

    manager = DockerContainerManager()
    proxy = NginxProxyManager() if uses_subdomain_urls() else None
    if proxy is not None:
        proxy.ensure_network()
    targets = _iter_target_envs(args.name)
    if not targets:
        print(_warning("Nothing to start."))
        return 0

    started_urls: dict[str, str] = {}
    print(_heading("Starting WebArena-Pro environments"))
    for name, image in targets:
        _ensure_local_native_image_if_needed(name, image, manager)
        ports = _build_ports(name)
        container_name = container_name_for_site(name)
        _print_site(name, f"Starting {_image(image)} ...", kind="progress", flush=True)
        info = manager.ensure_container_running(
            name=container_name,
            image=image,
            environment=website_environment(name, exp_hash=active_exp_hash()),
            ports=ports,
            labels=labels_for_site(name, exp_hash=active_exp_hash()),
            network=_network_name(),
            volumes=site_volume_overrides(name) or None,
            run_options=site_container_run_overrides(name) or None,
            post_start=lambda container, _name=name: post_start_site_setup(_name, container),
            log=lambda msg, _name=name: _print_site(_name, msg, kind="log", flush=True),
        )
        url = (
            _public_url(name)
            if uses_subdomain_urls()
            else manager.get_container_url(
                name=container_name,
                preferred_container_ports=_preferred_ports(name),
            )
        )

        _print_site(
            name,
            f"{_label('status')} {_format_status(info.status)}  "
            f"{_label('health')} {_format_health(info.health)}",
        )
        if url:
            _print_site(name, f"{_label('url')} {_url(url)}")
            started_urls[name] = url

    _reload_proxy_if_needed(
        proxy,
        log=lambda msg: _print_site("proxy", msg, kind="log", flush=True),
    )

    if started_urls:
        _wait_for_ready_sites(
            started_urls,
            timeout_seconds=float(getattr(args, "wait_timeout", DEFAULT_START_WAIT_SECONDS)),
        )

    if getattr(args, "login", False) or getattr(args, "auto_login", False):
        _auto_login_started_sites(
            started_urls,
            auth_dir=Path(args.auth_dir),
            browser_name=args.login_browser,
            headless=not args.headed,
            max_attempts=args.login_max_attempts,
        )

    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    manager = DockerContainerManager()
    proxy = NginxProxyManager() if uses_subdomain_urls() else None
    stop_all = _targets_all(args.name)
    targets = _iter_target_envs(args.name)
    if not targets:
        print(_warning("Nothing to stop."))
        return 0

    print(_heading("Stopping WebArena-Pro environments"))
    for name, _ in targets:
        container_name = container_name_for_site(name)
        manager.stop_container(container_name)
        _print_site(
            name,
            f"Stopped {_value(container_name)} {_muted('(if it existed)')}",
            kind="success",
        )
    if proxy is not None:
        if stop_all:
            proxy.stop_proxy(
                log=lambda msg: _print_site("proxy", msg, kind="log", flush=True),
            )
        else:
            _reload_proxy_if_needed(
                proxy,
                log=lambda msg: _print_site("proxy", msg, kind="log", flush=True),
            )
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    manager = DockerContainerManager()
    proxy = NginxProxyManager() if uses_subdomain_urls() else None
    if proxy is not None:
        proxy.ensure_network()
    targets = _iter_target_envs(args.name)
    if not targets:
        print(_warning("Nothing to restart."))
        return 0

    print(_heading("Restarting WebArena-Pro environments"))
    for name, image in targets:
        _ensure_local_native_image_if_needed(name, image, manager)
        ports = _build_ports(name)
        container_name = container_name_for_site(name)
        _print_site(name, f"Restarting {_image(image)} ...", kind="progress", flush=True)
        info = manager.reset_container(
            name=container_name,
            image=image,
            environment=website_environment(name, exp_hash=active_exp_hash()),
            ports=ports,
            labels=labels_for_site(name, exp_hash=active_exp_hash()),
            network=_network_name(),
            log=lambda msg, _name=name: _print_site(_name, msg, kind="log", flush=True),
        )
        url = (
            _public_url(name)
            if uses_subdomain_urls()
            else manager.get_container_url(
                name=container_name,
                preferred_container_ports=_preferred_ports(name),
            )
        )

        _print_site(
            name,
            f"Restarted {_value(info.name)}  "
            f"{_label('status')} {_format_status(info.status)}  "
            f"{_label('health')} {_format_health(info.health)}",
            kind="success",
        )
        if url:
            _print_site(name, f"{_label('url')} {_url(url)}")

    _reload_proxy_if_needed(
        proxy,
        log=lambda msg: _print_site("proxy", msg, kind="log", flush=True),
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    manager = DockerContainerManager()
    container_name = container_name_for_site(args.name)
    try:
        info = manager.get_container_info(container_name)
    except docker.errors.NotFound:
        print(_error(f"No container found with name '{container_name}'."))
        return 1

    url = (
        _public_url(args.name)
        if uses_subdomain_urls()
        else manager.get_container_url(
            name=container_name,
            preferred_container_ports=_preferred_ports(args.name),
        )
    )

    print(_heading(f"Environment status: {args.name}"))
    print(f"  {_label('Name')}    {_value(info.name)}")
    print(f"  {_label('Status')}  {_format_status(info.status)}")
    print(f"  {_label('Health')}  {_format_health(info.health)}")
    if url:
        print(f"  {_label('URL')}     {_url(url)}")

    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .dashboard_server import start_dashboard_server

    start_dashboard_server(host=args.host, port=args.port)
    return 0


def _add_dashboard_server_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind the website dashboard server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Public reverse-proxy port for dashboard and environment subdomains.",
    )


def _find_local_webarena_pro_bgym_src() -> Path | None:
    """Find a sibling `webarena-pro-bgym/src` checkout for local development."""
    roots: list[Path] = []
    for root in (Path.cwd(), Path(__file__).resolve()):
        for parent in (root, *root.parents):
            if parent not in roots:
                roots.append(parent)

    for parent in roots:
        candidate = parent / "webarena-pro-bgym" / "src" / "webarena_pro_bgym" / "run_cli.py"
        if candidate.exists():
            return candidate.parent.parent
    return None


def _run_bgym_module(args: list[str], *, source_root: Path) -> int:
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{source_root}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(source_root)
    )
    completed = subprocess.run(
        [sys.executable, "-m", "webarena_pro_bgym.run_cli", *args],
        env=env,
        check=False,
    )
    return int(completed.returncode)


def cmd_run(args: argparse.Namespace) -> int:
    source_root = _find_local_webarena_pro_bgym_src()
    if source_root is not None:
        return _run_bgym_module(args.args, source_root=source_root)

    try:
        from webarena_pro_bgym.run_cli import main as run_main
    except ImportError as error:
        raise SystemExit(
            "The 'webarena-pro run' command requires the webarena-pro-bgym package to be "
            "installed, or a sibling 'webarena-pro-bgym/src' checkout to be present."
        ) from error

    return int(run_main(args.args))


def cmd_help(args: argparse.Namespace) -> int:
    args.parser.print_help()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = _ColorArgumentParser(
        prog="webarena-pro",
        description="CLI to manage WebArena-Pro Docker environments.",
    )

    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        required=True,
        parser_class=_ColorArgumentParser,
    )

    p_env = subparsers.add_parser(
        "env",
        help="Manage WebArena-Pro environments.",
    )
    env_subparsers = p_env.add_subparsers(
        title="env commands",
        dest="env_command",
        required=True,
        parser_class=_ColorArgumentParser,
    )

    # list
    p_list = env_subparsers.add_parser(
        "list",
        help="List known WebArena-Pro environments.",
    )
    p_list.set_defaults(func=cmd_list)

    # pull
    p_pull = env_subparsers.add_parser(
        "pull",
        help="Pull or update Docker images from the registry, including local images.",
    )
    p_pull.add_argument(
        "name",
        metavar="NAME|all",
        help="Environment name to pull, or 'all' for every known environment.",
    )
    p_pull.set_defaults(func=cmd_pull)

    # start
    p_start = env_subparsers.add_parser(
        "start",
        help="Start (or create) a container for an environment.",
    )
    p_start.add_argument(
        "name",
        nargs="+",
        metavar="NAME|all",
        help=(
            "Environment name(s) to start, or 'all' for every known environment. "
            "Example: x-lite minerva-lite"
        ),
    )
    p_start.add_argument(
        "--login",
        action="store_true",
        help=(
            "After starting the selected environment(s), log in with the default "
            "account and write a Playwright storage-state file."
        ),
    )
    p_start.add_argument(
        "--auto_login",
        "--auto-login",
        dest="auto_login",
        action="store_true",
        help=(
            "After `env start all`, log into every started environment and "
            "write Playwright storage-state files."
        ),
    )
    p_start.add_argument(
        "--auth-dir",
        default=DEFAULT_AUTH_DIR,
        help=f"Directory for storage-state files when login is enabled. Default: {DEFAULT_AUTH_DIR}",
    )
    p_start.add_argument(
        "--login-browser",
        default=DEFAULT_LOGIN_BROWSER,
        help=f"Playwright browser to use for login. Default: {DEFAULT_LOGIN_BROWSER}",
    )
    p_start.add_argument(
        "--login-max-attempts",
        type=int,
        default=DEFAULT_LOGIN_MAX_ATTEMPTS,
        help=f"Maximum login attempts per site. Default: {DEFAULT_LOGIN_MAX_ATTEMPTS}",
    )
    p_start.add_argument(
        "--headed",
        action="store_true",
        help="Run the login browser headed instead of headless.",
    )
    p_start.add_argument(
        "--wait-timeout",
        type=float,
        default=DEFAULT_START_WAIT_SECONDS,
        metavar="SECONDS",
        help=(
            "Seconds to wait for each started website URL to stop returning server errors. "
            f"Default: {DEFAULT_START_WAIT_SECONDS:g}"
        ),
    )
    p_start.set_defaults(func=cmd_start)

    # stop
    p_stop = env_subparsers.add_parser(
        "stop",
        help="Stop and remove the container for an environment.",
    )
    p_stop.add_argument(
        "name",
        nargs="+",
        metavar="NAME|all",
        help=(
            "Environment name(s) to stop, or 'all' for every known environment. "
            "Example: x-lite minerva-lite"
        ),
    )
    p_stop.set_defaults(func=cmd_stop)

    # restart
    p_restart = env_subparsers.add_parser(
        "restart",
        help="Reset the container for an environment (stop + start).",
    )
    p_restart.add_argument(
        "name",
        metavar="NAME|all",
        help="Environment name to restart, or 'all' for every known environment.",
    )
    p_restart.set_defaults(func=cmd_restart)

    # status
    p_status = env_subparsers.add_parser(
        "status",
        help="Show status and URL for an environment container.",
    )
    _add_common_name_argument(p_status, help="Environment name to inspect.")
    p_status.set_defaults(func=cmd_status)

    # dashboard
    p_env_dashboard = env_subparsers.add_parser(
        "dashboard",
        help="Run the website environment viewer.",
        description="Run the local dashboard for starting, stopping, and opening website environments.",
    )
    _add_dashboard_server_args(p_env_dashboard)
    p_env_dashboard.set_defaults(func=cmd_serve)

    # serve
    p_serve = subparsers.add_parser(
        "serve",
        help="Alias for 'webarena-pro env dashboard'.",
        description="Alias for 'webarena-pro env dashboard'.",
    )
    _add_dashboard_server_args(p_serve)
    p_serve.set_defaults(func=cmd_serve)

    p_run = subparsers.add_parser(
        "run",
        help="Run evaluations or open the local worker/study dashboard.",
    )
    p_run.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        metavar="ARGS",
        help="Arguments forwarded to 'webarena-pro run'. Use 'dashboard' to open the worker/study dashboard.",
    )
    p_run.set_defaults(func=cmd_run)

    p_help = subparsers.add_parser(
        "help",
        help="Show top-level help.",
    )
    p_help.set_defaults(func=cmd_help, parser=parser)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # `argparse` does not allow a subparser with REMAINDER to start with an
    # option-looking token like `--site`, so handle `webarena-pro run ...`
    # before the generic parser sees it.
    if argv and argv[0] == "run":
        return int(cmd_run(argparse.Namespace(args=argv[1:])))

    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return int(func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
