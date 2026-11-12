import hashlib
import os
import re
from urllib.parse import urlparse

WEBSITES_IMAGES = {
    "password-manager": "webarenapro/password-manager:latest",
    "nextcloud": "webarenapro/nextcloud:latest",
    "flight-search": "webarenapro/flight-search:latest",
    "firefly": "webarenapro/firefly:latest",
    "travelmap": "webarenapro/travelmap:latest",
    "jobportal": "webarenapro/jobportal:latest",
    "thunderbird": "webarenapro/thunderbird:latest",
    "mattermost": "webarenapro/mattermost:latest",
    "immich": "webarenapro/immich:latest",
    "metabase": "webarenapro/metabase:latest",
    "mydrive": "webarenapro/mydrive:latest",
    "notion": "webarenapro/notion:latest",
    "yt-lite": "webarenapro/yt-lite:latest",
    "x-lite": "webarenapro/x-lite:latest",
    "minerva-lite": "webarenapro/minerva-lite:latest",
    "acidwave": "webarenapro/acidwave:latest",
    "peppermint": "webarenapro/peppermint:latest",
    "penpot": "webarenapro/penpot:latest",
    "pipedrive": "webarenapro/pipedrive:latest",
    "erp-next": "webarenapro/erp-next:latest",
}

WEBSITES_CONTAINER_PORTS = {
    "password-manager": 8000,
    "nextcloud": 80,
    "flight-search": 7860,
    "firefly": 8080,
    "travelmap": 4230,
    "jobportal": 8000,
    "thunderbird": 80,
    "mattermost": 8065,
    "immich": 2283,
    "metabase": 3000,
    "mydrive": 7860,
    "notion": 3000,
    "yt-lite": 7860,
    "x-lite": 7860,
    "minerva-lite": 8000,
    "acidwave": 80,
    "peppermint": 3000,
    "penpot": 9001,
    "pipedrive": 4520,
    "erp-next": 8000,
}

URL_MODE_ENV_VAR = "WP_URL_MODE"
DEFAULT_URL_MODE = "subdomain"
DIRECT_URL_MODE = "port"
SUBDOMAIN_URL_MODE = "subdomain"
EXP_HASH_ENV_VAR = "WP_EXP_HASH"
DEFAULT_EXP_HASH = "local"
WEB_SERVER_URL_ENV_VAR = "WP_WEB_SERVER_URL"
WEB_SERVER_SCHEME_ENV_VAR = "WP_WEB_SERVER_SCHEME"
WEB_SERVER_DOMAIN_ENV_VAR = "WP_WEB_SERVER_DOMAIN"
WEB_SERVER_PORT_ENV_VAR = "WP_WEB_SERVER_PORT"
WEB_SERVER_BIND_HOST_ENV_VAR = "WP_WEB_SERVER_BIND_HOST"
DEFAULT_WEB_SERVER_SCHEME = "http"
DEFAULT_WEB_SERVER_DOMAIN = "localhost"
DEFAULT_WEB_SERVER_PORT = "8080"
DEFAULT_WEB_SERVER_BIND_HOST = "127.0.0.1"

LABEL_PREFIX = "webarena-pro-core"
LABEL_MANAGED = f"{LABEL_PREFIX}.managed"
LABEL_SITE = f"{LABEL_PREFIX}.site"
LABEL_EXP_HASH = f"{LABEL_PREFIX}.exp-hash"
LABEL_UPSTREAM_PORT = f"{LABEL_PREFIX}.upstream-port"

WEBSITES_ADDITIONAL_HOST_PORT_ENV_VARS = {
    "mattermost": {
        "8443/tcp": "WP_MATTERMOST_CALLS_HOST_PORT",
        "8443/udp": "WP_MATTERMOST_CALLS_HOST_PORT",
    },
    "peppermint": {
        "5003/tcp": "WP_PEPPERMINT_API_HOST_PORT",
    },
}

_ADDITIONAL_HOST_PORT_DEFAULTS = {
    "mattermost": {
        "8443/tcp": 8443,
        "8443/udp": 8443,
    },
    "peppermint": {
        "5003/tcp": 5003,
    },
}

WEBSITES_ADDITIONAL_PORTS = {
    name: {
        container_port: int(
            os.environ.get(
                WEBSITES_ADDITIONAL_HOST_PORT_ENV_VARS[name][container_port],
                default,
            )
        )
        for container_port, default in defaults.items()
    }
    for name, defaults in _ADDITIONAL_HOST_PORT_DEFAULTS.items()
}

WEBSITES_HOST_PORT_ENV_VARS = {
    "password-manager": "WP_PASSWORD_MANAGER_HOST_PORT",
    "nextcloud": "WP_NEXTCLOUD_HOST_PORT",
    "flight-search": "WP_FLIGHT_SEARCH_HOST_PORT",
    "firefly": "WP_FIREFLY_HOST_PORT",
    "travelmap": "WP_TRAVELMAP_HOST_PORT",
    "jobportal": "WP_JOBPORTAL_HOST_PORT",
    "thunderbird": "WP_THUNDERBIRD_HOST_PORT",
    "mattermost": "WP_MATTERMOST_HOST_PORT",
    "immich": "WP_IMMICH_HOST_PORT",
    "metabase": "WP_METABASE_HOST_PORT",
    "mydrive": "WP_MYDRIVE_HOST_PORT",
    "notion": "WP_NOTION_HOST_PORT",
    "yt-lite": "WP_YT_LITE_HOST_PORT",
    "x-lite": "WP_X_LITE_HOST_PORT",
    "minerva-lite": "WP_MINERVA_LITE_HOST_PORT",
    "acidwave": "WP_ACIDWAVE_HOST_PORT",
    "peppermint": "WP_PEPPERMINT_HOST_PORT",
    "penpot": "WP_PENPOT_HOST_PORT",
    "pipedrive": "WP_PIPEDRIVE_HOST_PORT",
    "erp-next": "WP_ERP_NEXT_HOST_PORT",
}

_HOST_PORT_DEFAULTS = {
    "password-manager": 3201,
    "nextcloud": 3101,
    "flight-search": 3001,
    "firefly": 4801,
    "travelmap": 4701,
    "jobportal": 4601,
    "thunderbird": 5201,
    "mattermost": 5101,
    "immich": 5001,
    "metabase": 6101,
    "mydrive": 6001,
    "notion": 7301,
    "yt-lite": 7201,
    "x-lite": 7101,
    "minerva-lite": 7001,
    "acidwave": 9401,
    "peppermint": 9301,
    "penpot": 9001,
    "pipedrive": 9101,
    "erp-next": 9201,
}

WEBSITES_HOST_PORTS = {
    name: int(os.environ.get(WEBSITES_HOST_PORT_ENV_VARS[name], default))
    for name, default in _HOST_PORT_DEFAULTS.items()
}

def site_env_var_key(site: str) -> str:
    """Return the normalized env-var token for a website name."""
    return site.upper().replace("-", "_")


def _sanitize_token(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip())
    sanitized = sanitized.strip("-._")
    return sanitized or DEFAULT_EXP_HASH


def _sanitize_dns_label(value: str) -> str:
    label = re.sub(r"[^a-z0-9-]+", "-", str(value).strip().lower())
    label = re.sub(r"-+", "-", label).strip("-")
    label = label or DEFAULT_EXP_HASH
    if len(label) <= 63:
        return label
    digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:8]
    return f"{label[:54].rstrip('-')}-{digest}"


def active_url_mode(mode: str | None = None) -> str:
    raw = (
        mode
        if mode is not None
        else os.environ.get(URL_MODE_ENV_VAR, DEFAULT_URL_MODE)
    )
    normalized = str(raw).strip().lower()
    if normalized in {"", "subdomain", "domain", "host", "proxy"}:
        return SUBDOMAIN_URL_MODE
    if normalized in {"port", "ports", "direct", "localhost"}:
        return DIRECT_URL_MODE
    raise ValueError(
        f"Unsupported {URL_MODE_ENV_VAR}={raw!r}; expected 'subdomain' or 'port'."
    )


def uses_subdomain_urls(mode: str | None = None) -> bool:
    return active_url_mode(mode) == SUBDOMAIN_URL_MODE


def active_exp_hash(exp_hash: str | None = None) -> str:
    if exp_hash is not None:
        return _sanitize_token(exp_hash)
    return _sanitize_token(
        os.environ.get(EXP_HASH_ENV_VAR)
        or DEFAULT_EXP_HASH
    )


def _parsed_web_server_url():
    raw = os.environ.get(WEB_SERVER_URL_ENV_VAR)
    if not raw or not raw.strip():
        return None
    value = raw.strip()
    if "://" not in value:
        value = f"{DEFAULT_WEB_SERVER_SCHEME}://{value}"
    return urlparse(value)


def web_server_scheme() -> str:
    parsed = _parsed_web_server_url()
    if parsed is not None and parsed.scheme:
        return parsed.scheme
    return os.environ.get(WEB_SERVER_SCHEME_ENV_VAR, DEFAULT_WEB_SERVER_SCHEME).strip()


def web_server_domain() -> str:
    parsed = _parsed_web_server_url()
    if parsed is not None and parsed.hostname:
        return parsed.hostname
    return os.environ.get(WEB_SERVER_DOMAIN_ENV_VAR, DEFAULT_WEB_SERVER_DOMAIN).strip()


def web_server_port() -> int:
    parsed = _parsed_web_server_url()
    if parsed is not None:
        if parsed.port is not None:
            return int(parsed.port)
        if parsed.scheme == "http":
            return 80
        if parsed.scheme == "https":
            return 443
    return int(os.environ.get(WEB_SERVER_PORT_ENV_VAR, DEFAULT_WEB_SERVER_PORT))


def web_server_bind_host() -> str:
    return os.environ.get(WEB_SERVER_BIND_HOST_ENV_VAR, DEFAULT_WEB_SERVER_BIND_HOST)


def _format_url(*, scheme: str, host: str, port: int | None = None) -> str:
    if (
        port is None
        or (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def website_subdomain_label(site: str, *, exp_hash: str | None = None) -> str:
    site_label = _sanitize_dns_label(site)
    hash_label = _sanitize_dns_label(active_exp_hash(exp_hash))
    label = f"{site_label}--{hash_label}"
    if len(label) <= 63:
        return label
    digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:8]
    available = 63 - len(digest) - 3
    site_budget = max(1, min(len(site_label), available // 2))
    hash_budget = max(1, available - site_budget)
    return (
        f"{site_label[:site_budget].rstrip('-')}--"
        f"{hash_label[:hash_budget].rstrip('-')}-{digest}"
    )


def website_hostname(
    site: str,
    *,
    exp_hash: str | None = None,
    base_domain: str | None = None,
) -> str:
    domain = web_server_domain() if base_domain is None else str(base_domain).strip()
    return f"{website_subdomain_label(site, exp_hash=exp_hash)}.{domain}"


def dashboard_hostname(*, base_domain: str | None = None) -> str:
    domain = web_server_domain() if base_domain is None else str(base_domain).strip()
    return f"dashboard.{domain}"


def build_website_url(
    site: str,
    *,
    exp_hash: str | None = None,
    mode: str | None = None,
    host_port: int | None = None,
    base_domain: str | None = None,
) -> str:
    if active_url_mode(mode) == DIRECT_URL_MODE:
        resolved_port = int(
            WEBSITES_HOST_PORTS[site] if host_port is None else host_port
        )
        return f"http://localhost:{resolved_port}"

    return _format_url(
        scheme=web_server_scheme(),
        host=website_hostname(site, exp_hash=exp_hash, base_domain=base_domain),
        port=web_server_port(),
    )


def build_dashboard_url(*, base_domain: str | None = None) -> str:
    return _format_url(
        scheme=web_server_scheme(),
        host=dashboard_hostname(base_domain=base_domain),
        port=web_server_port(),
    )


WEBSITES_FIXED_URLS = {
    name: build_website_url(name)
    for name in WEBSITES_HOST_PORTS
}


def container_name_for_site(site: str, *, exp_hash: str | None = None) -> str:
    env_key = f"WP_{site_env_var_key(site)}_CONTAINER_NAME"
    override = os.environ.get(env_key)
    if override:
        return override
    resolved_hash = active_exp_hash(exp_hash)
    if resolved_hash == DEFAULT_EXP_HASH:
        return site
    return website_subdomain_label(site, exp_hash=resolved_hash)


def labels_for_site(site: str, *, exp_hash: str | None = None) -> dict[str, str]:
    return {
        LABEL_MANAGED: "website",
        LABEL_SITE: site,
        LABEL_EXP_HASH: active_exp_hash(exp_hash),
        LABEL_UPSTREAM_PORT: str(WEBSITES_CONTAINER_PORTS.get(site, 80)),
    }


def website_environment(
    site: str, *, exp_hash: str | None = None,
    public_url: str | None = None, eval_token: str | None = None,
) -> dict[str, str] | None:
    """Application settings for Core-managed or externally orchestrated sites.

    Explicit URLs/tokens allow Compose exporters to render deployment settings
    without changing process-global configuration or reading local secrets.
    """
    from webarena_pro_core.eval.api_registry import SITE_API_REGISTRY
    from webarena_pro_core.eval_token import resolve_eval_token

    public_url = public_url or build_website_url(site, exp_hash=exp_hash)
    public_root = public_url.rstrip("/")
    environment: dict[str, str] = {}
    uses_eval_token = any(
        spec.get("auth_mode") == "eval_token"
        for spec in SITE_API_REGISTRY.get(site, {}).values()
    )
    if uses_eval_token or "WP_EVAL_TOKEN" in os.environ:
        environment["WP_EVAL_TOKEN"] = eval_token if eval_token is not None else resolve_eval_token()

    if site == "flight-search":
        # Freeze the app clock at 2026-04-01 (backend/benchmark.py): prices carry
        # an advance-purchase multiplier and relative dates resolve against
        # "today", so every flight-search verifier anchor assumes this mode.
        environment["BENCHMARK_PASSCODE"] = "1"

    if site == "nextcloud":
        parsed = urlparse(public_root)
        trusted_domains = [
            "localhost",
            "*",
            "127.0.0.1",
            *(value for value in (parsed.hostname, parsed.netloc) if value),
        ]
        environment.update({
            "WP_NEXTCLOUD_URL": public_root,
            "WP_NEXTCLOUD_HOST_PORT": str(parsed.port or web_server_port()),
            "NEXTCLOUD_TRUSTED_DOMAINS": " ".join(dict.fromkeys(trusted_domains)),
        })
        # An external Office deployment is optional; bundled CODE is per worker.
        for key in ("WP_COLLABORA_URL", "WP_COLLABORA_INTERNAL_URL", "WP_NEXTCLOUD_CALLBACK_URL"):
            if os.environ.get(key):
                environment[key] = os.environ[key]
    elif site == "mattermost":
        websocket_url = public_root.replace("http://", "ws://", 1).replace(
            "https://",
            "wss://",
            1,
        )
        environment.update({
            "MM_PLUGINSETTINGS_ENABLE": "true",
            "MM_CALLS_ICE_HOST_OVERRIDE": os.environ.get(
                "MM_CALLS_ICE_HOST_OVERRIDE",
                os.environ.get("WP_MATTERMOST_CALLS_HOST", "127.0.0.1"),
            ),
            "MM_CALLS_ICE_HOST_PORT_OVERRIDE": os.environ.get(
                "MM_CALLS_ICE_HOST_PORT_OVERRIDE",
                str(website_published_ports(site, use_proxy=False)["8443/tcp"]),
            ),
            "MM_SERVICESETTINGS_SITEURL": public_root,
            "MM_SERVICESETTINGS_WEBSOCKETURL": websocket_url,
        })
        for key in ("MM_CALLS_UDP_SERVER_ADDRESS", "MM_CALLS_TCP_SERVER_ADDRESS"):
            if key in os.environ:
                environment[key] = os.environ[key]
    elif site == "firefly":
        environment.update({
            "APP_URL": public_root,
            "ASSET_URL": public_root,
        })
    elif site == "metabase":
        environment["MB_SITE_URL"] = public_root
    elif site == "pipedrive":
        # NextAuth otherwise derives callbacks from the standalone server's
        # bind address (0.0.0.0), which is not the browser's task origin.
        environment["NEXTAUTH_URL"] = public_root
    elif site == "penpot":
        environment["PENPOT_PUBLIC_URI"] = f"{public_root}/"
        if urlparse(public_root).scheme == "http":
            # Per-worker HTTP origins are not localhost. Browsers reject
            # Penpot's default Secure session cookie on these origins.
            flags = os.environ.get(
                "PENPOT_FLAGS",
                "enable-login-with-password disable-email-verification disable-smtp",
            ).split()
            flags = [flag for flag in flags if flag != "enable-secure-session-cookies"]
            if "disable-secure-session-cookies" not in flags:
                flags.append("disable-secure-session-cookies")
            environment["PENPOT_FLAGS"] = " ".join(flags)
    return environment or None


def build_website_ports(
    name: str,
    *,
    host_port: int | None = None,
    port_offset: int = 0,
) -> dict[str, int]:
    """Return the published port mapping for a website.

    ``port_offset`` is added to every additional published host port. This lets
    parallel workers reserve a consistent block of ports for multi-port sites
    such as Peppermint.
    """
    container_port = int(WEBSITES_CONTAINER_PORTS.get(name, 80))
    resolved_host_port = int(
        WEBSITES_HOST_PORTS[name] if host_port is None else host_port
    )
    ports = {f"{container_port}/tcp": resolved_host_port}

    for container_port, additional_host_port in WEBSITES_ADDITIONAL_PORTS.get(
        name, {}
    ).items():
        ports[str(container_port)] = int(additional_host_port) + int(port_offset)

    return ports


def website_published_ports(
    name: str,
    *,
    host_port: int | None = None,
    use_proxy: bool | None = None,
) -> dict[str, int] | None:
    """Return deployment bindings, including media that cannot use HTTP nginx.

    Calls uses the same host port for TCP and UDP. Worker environments explicitly
    assign that port; do not apply their offset a second time. Other sites keep
    their existing proxy/direct-port behavior.
    """
    resolved_host_port = int(
        os.environ.get(WEBSITES_HOST_PORT_ENV_VARS[name], WEBSITES_HOST_PORTS[name])
        if host_port is None else host_port
    )
    ports = build_website_ports(
        name,
        host_port=resolved_host_port,
        port_offset=resolved_host_port - int(WEBSITES_HOST_PORTS[name]),
    )
    for container_port, env_var in WEBSITES_ADDITIONAL_HOST_PORT_ENV_VARS.get(
        name, {}
    ).items():
        if env_var in os.environ:
            ports[container_port] = int(os.environ[env_var])
    if name == "mattermost":
        calls_port = ports["8443/tcp"]
        if not 1 <= calls_port <= 65535:
            raise ValueError("WP_MATTERMOST_CALLS_HOST_PORT must be between 1 and 65535")
        ports["8443/tcp"] = ports["8443/udp"] = calls_port

    proxy = uses_subdomain_urls() if use_proxy is None else use_proxy
    if proxy:
        return (
            {key: ports[key] for key in ("8443/tcp", "8443/udp")}
            if name == "mattermost" else None
        )
    return ports
