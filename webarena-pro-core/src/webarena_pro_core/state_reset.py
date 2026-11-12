from __future__ import annotations

import logging
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from . import (
    WEBSITES_HOST_PORTS,
    WEBSITES_HOST_PORT_ENV_VARS,
    WEBSITES_IMAGES,
    active_exp_hash,
    website_published_ports,
    container_name_for_site,
    labels_for_site,
    site_env_var_key,
    uses_subdomain_urls,
    web_server_bind_host,
    web_server_domain,
    web_server_port,
    website_environment,
    website_hostname,
)
from .website_metadata import deployed_website_url
from .runtime_locks import docker_lifecycle_slot, docker_timeout, runtime_lock

logger = logging.getLogger(__name__)

RESET_TOKEN_ENV_VAR = "WP_RESET_TOKEN"
RESET_REQUEST_TIMEOUT_SECONDS = 60
RESET_BACKEND_ENV_VAR = "WP_RESET_BACKEND"
DEFAULT_RESET_BACKEND = "auto"
STATE_RESTORE_BACKEND = "state"
CONTAINER_BACKEND = "container"
NOOP_BACKEND = "none"

# A site is ready only when the probe returns HTTP 200 and its body contains
# the configured sentinel. This avoids treating a live proxy or cold app
# server as a usable benchmark website.
READINESS_PROBES: dict[str, tuple[str, str]] = {
    "acidwave": ("/api/health", '"status":"ok"'),
    "firefly": ("/healthcheck", "ok"),
    "flight-search": ("/api/health", '"status":"ok"'),
    "erp-next": ("/api/method/ping", "pong"),
    "immich": ("/api/server/ping", "pong"),
    "nextcloud": ("/login", "password"),
    "jobportal": ("/", "<html"),
    "mattermost": ("/api/v4/system/ping", "status"),
    "metabase": ("/api/health", "status"),
    "penpot": ("/api/rpc/command/get-profile", "~:id"),
    "yt-lite": ("/", "yt-lite"),
}
RESET_SNAPSHOT_MARKERS: dict[str, str] = {
    "erp-next": "/opt/erpnext-seed/reset/ready",
    "nextcloud": "/opt/webarena-seed/ready",
}
READINESS_TIMEOUT_SECONDS = 240
RESET_SNAPSHOT_TIMEOUT_SECONDS = 240
SITE_READINESS_TIMEOUT_SECONDS: dict[str, int] = {
    "nextcloud": 20 * 60,
}
SITE_RESET_SNAPSHOT_TIMEOUT_SECONDS: dict[str, int] = {
    "erp-next": 20 * 60,
    "nextcloud": 20 * 60,
}
# Fast preseeded sites should not pay up to 1.5 seconds of polling delay.
READINESS_POLL_INTERVAL_SECONDS = 0.25

_SITE_RESET_ENDPOINTS: dict[str, tuple[tuple[str, str], ...]] = {
    "acidwave": (("POST", "/api/reset"),),
    "flight-search": (("POST", "/api/reset"),),
    "jobportal": (("POST", "/api/reset"),),
    "minerva-lite": (("GET", "/reset"),),
    "mydrive": (("POST", "/api/dev/reset"),),
    "notion": (("POST", "/api/reset"),),
    "password-manager": (("POST", "/api/reset"),),
    "travelmap": (("POST", "/api/reset"), ("POST", "/reset")),
    "x-lite": (("GET", "/reset"),),
}
_DEFAULT_RESET_ENDPOINTS = (("POST", "/api/reset"),)

_YT_LITE_RESET_SCRIPT = """
import json
import os
from pathlib import Path

from app import (
    DB_PATH,
    FINEVIDEO_DATA_PATH,
    THUMBNAIL_UPLOAD_DIR,
    VIDEO_UPLOAD_DIR,
    app,
    init_db,
)

with open(FINEVIDEO_DATA_PATH, "r", encoding="utf-8") as seed_file:
    seed_videos = json.load(seed_file)

keep_videos = {
    Path(video["video_path"]).name
    for video in seed_videos
    if video.get("video_path")
}
keep_thumbnails = {
    Path(video["thumbnail"]).name
    for video in seed_videos
    if video.get("thumbnail")
}

for db_path in (DB_PATH, f"{DB_PATH}-wal", f"{DB_PATH}-shm"):
    if os.path.exists(db_path):
        os.remove(db_path)

for upload_dir, keep_names in (
    (VIDEO_UPLOAD_DIR, keep_videos),
    (THUMBNAIL_UPLOAD_DIR, keep_thumbnails),
):
    path = Path(upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_file() and child.name not in keep_names:
            child.unlink()

with app.app_context():
    init_db()
""".strip()

_PENPOT_RESET_SCRIPT = """
set -euo pipefail
bash /usr/local/bin/webarena-reset-state
""".strip()


@dataclass(frozen=True)
class SiteRequestTarget:
    url: str
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class SiteResetResult:
    site: str
    method: str
    url: str
    status_code: int


@dataclass(frozen=True)
class DockerExecResetSpec:
    command: tuple[str, ...]
    workdir: str | None = None
    user: str | None = None
    environment: dict[str, str] | None = None


_DOCKER_EXEC_RESET_SPECS: dict[str, DockerExecResetSpec] = {
    "erp-next": DockerExecResetSpec(
        command=("bash", "/usr/local/bin/webarena-reset-state"),
    ),
    "firefly": DockerExecResetSpec(
        command=("bash", "/usr/local/bin/webarena-reset-state"),
    ),
    "immich": DockerExecResetSpec(
        command=("bash", "/usr/local/bin/webarena-reset-state"),
    ),
    "mattermost": DockerExecResetSpec(
        command=("bash", "/usr/local/bin/webarena-reset-state"),
    ),
    "metabase": DockerExecResetSpec(
        command=("bash", "/usr/local/bin/webarena-reset-state"),
    ),
    "nextcloud": DockerExecResetSpec(
        command=("bash", "/usr/local/bin/webarena-reset-state"),
    ),
    "penpot": DockerExecResetSpec(
        command=("bash", "-lc", _PENPOT_RESET_SCRIPT),
    ),
    "peppermint": DockerExecResetSpec(
        command=("bash", "/usr/local/bin/webarena-reset-state"),
    ),
    "pipedrive": DockerExecResetSpec(
        command=("node", "scripts/restore-seed-if-empty.js"),
        workdir="/app",
        environment={"RESET_TO_SEED_ON_STARTUP": "1"},
    ),
    "thunderbird": DockerExecResetSpec(
        command=("bash", "/usr/local/bin/webarena-reset-state"),
    ),
    "yt-lite": DockerExecResetSpec(
        command=("python", "-c", _YT_LITE_RESET_SCRIPT),
        workdir="/app",
    ),
}

STATE_RESTORE_SITES = frozenset(_SITE_RESET_ENDPOINTS) | frozenset(
    _DOCKER_EXEC_RESET_SPECS
)
# These still have explicit state-restore scripts, but measured reset time is
# slower than container recreation, so auto reset prefers the container path.
CONTAINER_PREFERRED_RESET_SITES = frozenset(
    {
        "acidwave",
        "immich",
        "metabase",
        "penpot",
        "peppermint",
        "thunderbird",
        "x-lite",
    }
)
RESET_API_SITES = frozenset(WEBSITES_IMAGES)
CONTAINER_RECREATE_RESET_SITES = (
    RESET_API_SITES - STATE_RESTORE_SITES
) | CONTAINER_PREFERRED_RESET_SITES


def reset_token_for_site(site: str) -> str | None:
    site_key = site_env_var_key(site)
    return (
        os.environ.get(f"WP_{site_key}_RESET_TOKEN")
        or os.environ.get(RESET_TOKEN_ENV_VAR)
        or None
    )


def site_request_target(site: str, path: str) -> SiteRequestTarget:
    public_url = deployed_website_url(site).rstrip("/")
    explicit_url = os.environ.get(f"WP_{site_env_var_key(site)}_URL")
    domain = web_server_domain()
    should_use_public_url = explicit_url or domain not in {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
    }

    if should_use_public_url:
        return SiteRequestTarget(urljoin(f"{public_url}/", path.lstrip("/")))

    if uses_subdomain_urls():
        proxy_host = web_server_bind_host()
        if proxy_host in {"", "0.0.0.0", "::"}:
            proxy_host = "127.0.0.1"
        port = web_server_port()
        return SiteRequestTarget(
            url=f"http://{proxy_host}:{port}{path}",
            headers={"Host": f"{website_hostname(site)}:{port}"},
        )

    return SiteRequestTarget(urljoin(f"{public_url}/", path.lstrip("/")))


def reset_endpoints_for_site(site: str) -> tuple[tuple[str, str], ...]:
    return _SITE_RESET_ENDPOINTS.get(site, _DEFAULT_RESET_ENDPOINTS)


def reset_backend_for_site(site: str, backend: str | None = None) -> str:
    """Resolve the reset backend for ``site``.

    ``auto`` uses in-place restoration when it is faster and supported, then
    falls back to container recreation for all other registered sites.
    """
    raw = (
        os.environ.get(RESET_BACKEND_ENV_VAR, DEFAULT_RESET_BACKEND)
        if backend is None
        else backend
    )
    normalized = str(raw).strip().lower()
    if normalized in {"", "auto"}:
        if site in CONTAINER_PREFERRED_RESET_SITES:
            return CONTAINER_BACKEND
        return (
            STATE_RESTORE_BACKEND if site in STATE_RESTORE_SITES else CONTAINER_BACKEND
        )
    if normalized in {"container", "docker"}:
        return CONTAINER_BACKEND
    if normalized in {"state", "http", "restore", "app"}:
        return STATE_RESTORE_BACKEND
    if normalized in {"none", "noop", "off"}:
        return NOOP_BACKEND
    raise RuntimeError(
        f"Unsupported {RESET_BACKEND_ENV_VAR}={raw!r}; expected auto, "
        "container, state, or none."
    )


def reset_site(
    site: str,
    *,
    backend: str | None = None,
    timeout_seconds: int = RESET_REQUEST_TIMEOUT_SECONDS,
    endpoints: Iterable[tuple[str, str]] | None = None,
    docker_client: Any | None = None,
    container_manager: Any | None = None,
    proxy_manager: Any | None = None,
    exp_hash: str | None = None,
) -> SiteResetResult | None:
    """Reset any site supported by the package-level reset API.

    Fast state-restore sites use URL or Docker-exec restore. Sites whose
    container boot is faster than their restore script, and any remaining
    supported sites, use container recreation on the environment host. The
    function waits for both the packaged reset snapshot and the site's HTTP
    readiness probe before returning.
    """
    if site not in RESET_API_SITES:
        raise RuntimeError(
            f"Site '{site}' is not supported by the package-level reset API."
        )

    resolved_backend = reset_backend_for_site(site, backend)
    if resolved_backend == NOOP_BACKEND:
        logger.info("[reset] %s: reset backend is none; skipping", site)
        return None
    if resolved_backend == STATE_RESTORE_BACKEND:
        return restore_site_state_and_wait(
            site,
            timeout_seconds=timeout_seconds,
            endpoints=endpoints,
            docker_client=docker_client,
            container_manager=container_manager,
            proxy_manager=proxy_manager,
            exp_hash=exp_hash,
        )

    return reset_site_container(
        site,
        container_manager=container_manager,
        proxy_manager=proxy_manager,
        exp_hash=exp_hash,
    )


def recreate_site_container(
    site: str,
    *,
    container_manager: Any | None = None,
    proxy_manager: Any | None = None,
    exp_hash: str | None = None,
) -> SiteResetResult:
    """Force container recreation for a registered website image.

    This is primarily useful as a bootstrap fallback for worker-local URLs:
    the first task on a fresh worker may not have a running app to reset in
    place yet, so callers can recreate the worker container once and then use
    faster state restore on later tasks.
    """
    if site not in WEBSITES_IMAGES:
        raise RuntimeError(f"Site '{site}' does not have a registered website image.")
    return _reset_site_via_container_recreate(
        site,
        container_manager=container_manager,
        proxy_manager=proxy_manager,
        exp_hash=exp_hash,
    )


def reset_site_container(
    site: str,
    *,
    container_manager: Any | None = None,
    proxy_manager: Any | None = None,
    exp_hash: str | None = None,
    timeout_seconds: int | None = None,
) -> SiteResetResult:
    """Recreate a site's container and wait until it is fully usable."""
    started_at = time.monotonic()
    with _reset_phase(site, "container_recreate"):
        result = recreate_site_container(
            site,
            container_manager=container_manager,
            proxy_manager=proxy_manager,
            exp_hash=exp_hash,
        )
    wait_until_site_ready(site, timeout_seconds=timeout_seconds)
    logger.info(
        "[reset] %s ready in %.1fs via %s",
        site,
        time.monotonic() - started_at,
        result.method,
    )
    return result


def restore_site_state(
    site: str,
    *,
    timeout_seconds: int = RESET_REQUEST_TIMEOUT_SECONDS,
    endpoints: Iterable[tuple[str, str]] | None = None,
    docker_client: Any | None = None,
) -> SiteResetResult:
    """Reset a running site in place through its packaged reset contract."""
    if site not in STATE_RESTORE_SITES:
        raise RuntimeError(
            f"Site '{site}' does not advertise package-level state restore support."
        )

    with runtime_lock(f"container:{container_name_for_site(site)}"), docker_lifecycle_slot():
        if site in _DOCKER_EXEC_RESET_SPECS and endpoints is None:
            return _restore_site_state_via_docker_exec(site, docker_client=docker_client)

        return _restore_site_state_via_http(
            site,
            timeout_seconds=timeout_seconds,
            endpoints=endpoints,
        )


def restore_site_state_and_wait(
    site: str,
    *,
    timeout_seconds: int = RESET_REQUEST_TIMEOUT_SECONDS,
    readiness_timeout_seconds: int | None = None,
    endpoints: Iterable[tuple[str, str]] | None = None,
    docker_client: Any | None = None,
    container_manager: Any | None = None,
    proxy_manager: Any | None = None,
    exp_hash: str | None = None,
) -> SiteResetResult:
    """Restore a running site, bootstrapping its container when unavailable."""
    try:
        wait_until_reset_snapshot_ready(site, docker_client=docker_client)
        with _reset_phase(site, "state_restore"):
            result = restore_site_state(
                site,
                timeout_seconds=timeout_seconds,
                endpoints=endpoints,
                docker_client=docker_client,
            )
    except RuntimeError as error:
        if not state_restore_error_allows_container_bootstrap(error):
            raise
        logger.info(
            "[reset] %s state restore target is unavailable; bootstrapping "
            "worker container from image",
            site,
        )
        return reset_site_container(
            site,
            container_manager=container_manager,
            proxy_manager=proxy_manager,
            exp_hash=exp_hash,
            timeout_seconds=readiness_timeout_seconds,
        )

    wait_until_site_ready(
        site,
        timeout_seconds=readiness_timeout_seconds,
        wait_for_snapshot=False,
    )
    logger.info("[reset] %s restored via %s %s", site, result.method, result.url)
    return result


def state_restore_error_allows_container_bootstrap(error: RuntimeError) -> bool:
    """Return whether a restore failure indicates an unavailable worker site."""
    text = str(error).lower()
    unavailable_markers = (
        "connection refused",
        "failed to establish a new connection",
        "name or service not known",
        "nodename nor servname",
        "temporary failure in name resolution",
        "could not resolve",
        "no route to host",
        "connection reset",
        "timed out",
        "http 502",
        "http 503",
        "http 504",
        "bad gateway",
        "service unavailable",
        "gateway timeout",
        "no such container",
        "container not found",
        "container is not running",
        "is not running",
        "http 404",
        "404 client error",
    )
    return any(marker in text for marker in unavailable_markers)


def _reset_site_via_container_recreate(
    site: str,
    *,
    container_manager: Any | None = None,
    proxy_manager: Any | None = None,
    exp_hash: str | None = None,
) -> SiteResetResult:
    try:
        from .docker import DockerContainerManager
        from .nginx import NginxProxyManager, docker_network_name
    except ImportError as error:
        raise RuntimeError(
            f"webarena_pro_core / docker not importable; cannot reset '{site}': {error}"
        ) from error

    manager = container_manager or DockerContainerManager()
    use_proxy = uses_subdomain_urls()
    proxy = None
    network = None
    if use_proxy:
        network = docker_network_name()
        proxy = proxy_manager if proxy_manager is not None else NginxProxyManager()
        proxy.ensure_network()

    resolved_exp_hash = exp_hash_for_site(site, exp_hash=exp_hash)
    container_name = container_name_for_site(site, exp_hash=resolved_exp_hash)
    host_port = host_port_for_site(site)
    ports = website_published_ports(
        site, host_port=host_port, use_proxy=use_proxy
    )
    manager.reset_container(
        name=container_name,
        image=WEBSITES_IMAGES[site],
        environment=website_environment(site, exp_hash=resolved_exp_hash),
        ports=ports,
        labels=labels_for_site(site, exp_hash=resolved_exp_hash),
        network=network,
        volumes=site_volume_overrides(site),
        run_options=site_container_run_overrides(site),
        post_start=lambda container: post_start_site_setup(site, container),
        # Media ports can be occupied by unrelated RTC services. Fail instead
        # of removing another deployment to claim a Mattermost worker's port.
        remove_port_conflicts=bool(ports) and site != "mattermost",
    )

    if proxy is not None:
        ensure_proxy_serialized(proxy)

    return SiteResetResult(
        site=site,
        method="CONTAINER_RECREATE",
        url=f"container:{container_name}",
        status_code=0,
    )


def exp_hash_for_site(site: str, *, exp_hash: str | None = None) -> str:
    """Resolve a site-specific worker hash before the global experiment hash."""
    if exp_hash is None:
        exp_hash = os.environ.get(f"WP_{site_env_var_key(site)}_EXP_HASH")
    return active_exp_hash(exp_hash)


def host_port_for_site(site: str) -> int:
    """Resolve a site's host port dynamically from its environment override."""
    if site not in WEBSITES_HOST_PORTS:
        raise RuntimeError(f"No host port configured for site '{site}'")
    env_var = WEBSITES_HOST_PORT_ENV_VARS[site]
    return int(os.environ.get(env_var, WEBSITES_HOST_PORTS[site]))


def stop_site_container(
    site: str,
    *,
    container_manager: Any | None = None,
    proxy_manager: Any | None = None,
) -> None:
    """Remove the container backing ``site`` and refresh the local proxy."""
    try:
        from .docker import DockerContainerManager
        from .nginx import NginxProxyManager
    except ImportError as error:
        raise RuntimeError(
            f"webarena_pro_core / docker not importable; cannot stop '{site}': {error}"
        ) from error

    manager = container_manager or DockerContainerManager()
    container_name = container_name_for_site(site)
    logger.info("[reset] stopping container %s", container_name)
    manager.stop_container(container_name)

    if uses_subdomain_urls():
        try:
            proxy = proxy_manager if proxy_manager is not None else NginxProxyManager()
            ensure_proxy_serialized(proxy)
        except Exception:
            logger.debug("[reset] failed to refresh proxy after stop", exc_info=True)


def site_volume_overrides(site: str) -> dict[str, dict[str, str]]:
    """Return site-specific bind mounts required for reliable startup."""
    if site == "nextcloud":
        return {
            ensure_opcache_nojit_file(): {
                "bind": "/usr/local/etc/php/conf.d/opcache-recommended.ini",
                "mode": "ro",
            }
        }
    return {}


def site_container_run_overrides(site: str) -> dict[str, object]:
    """Return site-specific Docker run options."""
    # A small init process forwards termination to single-process apps and
    # shell/npm launchers, avoiding Docker's ten-second forced-stop fallback.
    if site in {
        "acidwave", "flight-search", "jobportal", "metabase", "minerva-lite", "mydrive",
        "password-manager", "pipedrive", "travelmap", "x-lite", "yt-lite",
    }:
        return {"init": True}
    if site == "penpot":
        return {
            "entrypoint": "/bin/sh",
            "command": [
                "-ec",
                # The image hardcodes flags in Supervisor's child process
                # environment, overriding Docker's per-worker cookie settings.
                "sed -i 's/PENPOT_FLAGS=\"[^\"]*\"/PENPOT_FLAGS=\"%(ENV_PENPOT_FLAGS)s\"/g' "
                "/etc/supervisor/conf.d/supervisord.conf\n"
                "exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf",
            ],
        }
    return {}


def post_start_site_setup(site: str, container: Any) -> None:
    """Apply setup that must run immediately after a site's container starts."""
    if site != "nextcloud":
        return

    result = container.exec_run(
        (
            "sh",
            "-lc",
            "mkdir -p /opt/webarena-seed && chown www-data:www-data /opt/webarena-seed",
        )
    )
    exit_code, output = _normalize_exec_result(result)
    if exit_code != 0:
        raise RuntimeError(
            "Failed to prepare Nextcloud reset snapshot directory in "
            f"{container_name_for_site(site)}: {_decode_exec_output(output)[:500]}"
        )


_OPCACHE_NOJIT_CONTENTS = "opcache.jit=0\nopcache.jit_buffer_size=0\n"


def ensure_opcache_nojit_file() -> str:
    """Create the user-scoped PHP opcache override used by Nextcloud."""
    path = os.path.join(
        tempfile.gettempdir(),
        f"wp-opcache-nojit-{os.getuid()}.ini",
    )
    try:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as file:
                if file.read() == _OPCACHE_NOJIT_CONTENTS:
                    return path
        with open(path, "w", encoding="utf-8") as file:
            file.write(_OPCACHE_NOJIT_CONTENTS)
    except OSError as error:
        raise RuntimeError(
            f"Failed to write opcache override at {path}: {error}"
        ) from error
    return path


def ensure_proxy_serialized(proxy: Any) -> None:
    """Serialize proxy configuration writes across worker processes."""
    from .nginx import nginx_container_name

    # Reuse the manager's lock, including for injected proxy implementations.
    with runtime_lock(f"proxy:{nginx_container_name()}"):
        proxy.ensure_proxy()


class NextcloudOfficeImageError(RuntimeError):
    """The deployed Nextcloud image cannot provide its Office readiness contract."""


def wait_until_site_ready(
    site: str,
    timeout_seconds: int | None = None,
    *,
    wait_for_snapshot: bool = True,
) -> None:
    """Wait until the site's HTTP endpoint and reset snapshot are ready."""
    path, sentinel = READINESS_PROBES.get(site, ("/", ""))
    target = site_request_target(site, path)
    effective_timeout = readiness_timeout_for_site(site, timeout_seconds)
    started_at = time.monotonic()
    deadline = started_at + effective_timeout
    container_name = container_name_for_site(site)
    host_header = (target.headers or {}).get("Host")
    logger.info(
        "[reset] %s phase=http_readiness container=%s GET %s Host=%r "
        "sentinel=%r timeout=%ss",
        site, container_name, target.url, host_header, sentinel, effective_timeout,
    )
    last_error = "probe not attempted"
    attempts = 0

    while (remaining := deadline - time.monotonic()) > 0:
        attempts += 1
        try:
            request = Request(target.url, headers=target.headers or {})
            with urlopen(request, timeout=min(5, remaining)) as response:
                status_code = int(getattr(response, "status", 200))
                body = response.read().decode("utf-8", errors="replace").lower()
            sentinel_found = not sentinel or sentinel in body
            if status_code == 200 and sentinel_found:
                if site == "nextcloud":
                    office = site_request_target(site, "/webarena-office-health.php")
                    office_request = Request(office.url, headers=office.headers or {})
                    office_remaining = deadline - time.monotonic()
                    if office_remaining <= 0:
                        last_error = "Office readiness: deadline exhausted after login"
                        continue
                    try:
                        with urlopen(office_request, timeout=min(5, office_remaining)) as response:
                            office_status = int(getattr(response, "status", 200))
                            office_body = response.read().decode("utf-8", errors="replace").strip()
                    except HTTPError as error:
                        if error.code == 404:
                            raise NextcloudOfficeImageError(
                                "Nextcloud Office readiness endpoint is missing. Rebuild/deploy "
                                "the Nextcloud image with bundled CODE before using this Core "
                                "version; existing published images cannot provide spreadsheet editing."
                            ) from error
                        details = error.read(500).decode("utf-8", errors="replace").strip()
                        if error.code == 503 and details.startswith("Office startup failed"):
                            raise NextcloudOfficeImageError(details) from error
                        raise
                    if office_status != 200 or office_body != "office-ready":
                        last_error = f"Office readiness: HTTP {office_status}: {office_body[:200]}"
                        time.sleep(min(READINESS_POLL_INTERVAL_SECONDS, max(0, deadline - time.monotonic())))
                        continue
                break
            last_error = (
                f"HTTP {status_code} "
                f"(sentinel={'found' if sentinel_found else 'absent'})"
            )
        except NextcloudOfficeImageError:
            raise
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
        time.sleep(min(
            READINESS_POLL_INTERVAL_SECONDS, max(0, deadline - time.monotonic())
        ))
    else:
        raise RuntimeError(
            f"Site '{site}' did not become ready within {effective_timeout}s "
            f"(phase=http_readiness, container={container_name}, "
            f"image={WEBSITES_IMAGES.get(site)}, GET {target.url}, Host={host_header!r}, "
            f"sentinel={sentinel!r}, last error: {last_error}, attempts: {attempts}, "
            f"elapsed: {time.monotonic() - started_at:.1f}s)"
        )

    logger.info(
        "[reset] %s phase=http_readiness ready after %.1fs (%d attempts)",
        site, time.monotonic() - started_at, attempts,
    )
    # Snapshot failures are a separate phase. Do not catch them as HTTP probe
    # failures and restart the snapshot's full timeout on every HTTP retry.
    if wait_for_snapshot:
        wait_until_reset_snapshot_ready(site)


@contextmanager
def _reset_phase(site: str, phase: str):
    """Keep reset phase timing in worker/prewarm logs, including failures."""
    started_at = time.monotonic()
    context = f"[reset] {site} phase={phase} container={container_name_for_site(site)}"
    logger.info("%s starting", context)
    try:
        yield
    except Exception as error:
        logger.warning(
            "%s failed after %.1fs: %s", context, time.monotonic() - started_at, error
        )
        raise
    else:
        logger.info("%s completed after %.1fs", context, time.monotonic() - started_at)


def readiness_timeout_for_site(
    site: str,
    timeout_seconds: int | None = None,
) -> int:
    if timeout_seconds is not None:
        return int(timeout_seconds)
    return SITE_READINESS_TIMEOUT_SECONDS.get(site, READINESS_TIMEOUT_SECONDS)


def reset_snapshot_timeout_for_site(
    site: str,
    timeout_seconds: int | None = None,
) -> int:
    if timeout_seconds is not None:
        return int(timeout_seconds)
    return SITE_RESET_SNAPSHOT_TIMEOUT_SECONDS.get(
        site,
        RESET_SNAPSHOT_TIMEOUT_SECONDS,
    )


def wait_until_reset_snapshot_ready(
    site: str,
    timeout_seconds: int | None = None,
    *,
    docker_client: Any | None = None,
) -> None:
    """Wait for an image's packaged reset snapshot marker when it has one."""
    marker = RESET_SNAPSHOT_MARKERS.get(site)
    if marker is None:
        return

    effective_timeout = reset_snapshot_timeout_for_site(site, timeout_seconds)
    started_at = time.monotonic()
    deadline = started_at + effective_timeout
    container_name = container_name_for_site(site)
    try:
        import docker
        from docker.errors import NotFound
    except ImportError:
        logger.debug("[reset] docker unavailable; skipping %s snapshot wait", site)
        return

    try:
        client = docker_client or docker.from_env(timeout=docker_timeout())
        container = client.containers.get(container_name)
    except NotFound:
        logger.debug("[reset] %s container absent; skipping snapshot wait", site)
        return
    except Exception:
        logger.debug("[reset] failed to inspect %s container", site, exc_info=True)
        return

    last_error = "marker not checked"
    logger.info(
        "[reset] %s phase=reset_snapshot container=%s marker=%s timeout=%ss",
        site, container_name, marker, effective_timeout,
    )
    while time.monotonic() < deadline:
        try:
            result = container.exec_run(("test", "-f", marker))
            exit_code, _ = _normalize_exec_result(result)
            if exit_code == 0:
                logger.info(
                    "[reset] %s phase=reset_snapshot ready after %.1fs",
                    site, time.monotonic() - started_at,
                )
                return
            last_error = f"{marker} absent"
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
        time.sleep(min(
            READINESS_POLL_INTERVAL_SECONDS, max(0, deadline - time.monotonic())
        ))

    raise RuntimeError(
        f"Site '{site}' reset snapshot marker {marker!r} was not ready "
        f"within {effective_timeout}s (phase=reset_snapshot, container={container_name}, "
        f"last error: {last_error}, elapsed: {time.monotonic() - started_at:.1f}s)"
    )


def _restore_site_state_via_http(
    site: str,
    *,
    timeout_seconds: int,
    endpoints: Iterable[tuple[str, str]] | None = None,
) -> SiteResetResult:
    token = reset_token_for_site(site)
    errors: list[str] = []
    for method, path in tuple(endpoints or reset_endpoints_for_site(site)):
        target = site_request_target(site, path)
        url = _append_token(target.url, token)
        request = Request(url, method=method, headers=target.headers or {})
        if method.upper() == "POST":
            request.data = b""

        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                status_code = int(getattr(response, "status", 200))
        except HTTPError as error:
            if error.code in {404, 405}:
                errors.append(f"{method} {url}: HTTP {error.code}")
                continue
            body = _read_error_body(error)
            raise RuntimeError(
                f"State restore for '{site}' failed via {method} {url}: "
                f"HTTP {error.code}: {body[:500]}"
            ) from error
        except URLError as error:
            errors.append(f"{method} {url}: {error.reason}")
            continue

        if 200 <= status_code < 300:
            return SiteResetResult(
                site=site,
                method=method,
                url=url,
                status_code=status_code,
            )
        if status_code in {404, 405}:
            errors.append(f"{method} {url}: HTTP {status_code}")
            continue
        raise RuntimeError(
            f"State restore for '{site}' failed via {method} {url}: HTTP {status_code}"
        )

    raise RuntimeError(
        f"State restore for '{site}' failed; tried reset endpoints. "
        f"Errors: {'; '.join(errors)}"
    )


def _restore_site_state_via_docker_exec(
    site: str,
    *,
    docker_client: Any | None = None,
) -> SiteResetResult:
    spec = _DOCKER_EXEC_RESET_SPECS[site]
    client = docker_client or _docker_client_from_env(site)
    container_name = container_name_for_site(site)

    try:
        container = client.containers.get(container_name)
        exec_result = container.exec_run(
            spec.command,
            workdir=spec.workdir,
            user=spec.user or "",
            environment=spec.environment,
        )
    except Exception as error:
        raise RuntimeError(
            f"State restore for '{site}' failed via docker exec in "
            f"container '{container_name}': {error}"
        ) from error

    exit_code, output = _normalize_exec_result(exec_result)
    if exit_code != 0:
        raise RuntimeError(
            f"State restore for '{site}' failed via docker exec in "
            f"container '{container_name}' with exit code {exit_code}: "
            f"{_decode_exec_output(output)[:500]}"
        )

    return SiteResetResult(
        site=site,
        method="DOCKER_EXEC",
        url=f"container:{container_name}",
        status_code=exit_code,
    )


def _docker_client_from_env(site: str) -> Any:
    try:
        import docker
    except ImportError as error:
        raise RuntimeError(
            f"Docker is not importable; cannot run state restore for '{site}'."
        ) from error

    return docker.from_env(timeout=docker_timeout())


def _normalize_exec_result(exec_result: Any) -> tuple[int, bytes | str | None]:
    if hasattr(exec_result, "exit_code"):
        return int(exec_result.exit_code), getattr(exec_result, "output", None)

    exit_code, output = exec_result
    return int(exit_code), output


def _decode_exec_output(output: bytes | str | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return str(output)


def _append_token(url: str, token: str | None) -> str:
    if not token:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'token': token})}"


def _read_error_body(error: HTTPError) -> str:
    try:
        return error.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
