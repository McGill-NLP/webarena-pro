from __future__ import annotations

import hashlib
import os
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import docker
from docker.errors import APIError, NotFound
from docker.types import Mount

from . import (
    LABEL_EXP_HASH,
    LABEL_MANAGED,
    LABEL_PREFIX,
    LABEL_SITE,
    LABEL_UPSTREAM_PORT,
    build_dashboard_url,
    dashboard_hostname,
    web_server_bind_host,
    web_server_port,
    website_hostname,
)

from .docker import DockerContainerManager, _LifecyclePending, _retry_lifecycle
from .runtime_locks import docker_lifecycle_slot, docker_timeout, runtime_lock

NETWORK_ENV_VAR = "WP_DOCKER_NETWORK"
NGINX_CONTAINER_ENV_VAR = "WP_NGINX_CONTAINER_NAME"
NGINX_IMAGE_ENV_VAR = "WP_NGINX_IMAGE"
DASHBOARD_HOST_ENV_VAR = "WP_DASHBOARD_HOST"
DASHBOARD_PORT_ENV_VAR = "WP_DASHBOARD_PORT"
DASHBOARD_UPSTREAM_HOST_ENV_VAR = "WP_DASHBOARD_UPSTREAM_HOST"
DEFAULT_NETWORK = "webarena-pro-core"
DEFAULT_NGINX_CONTAINER = "webarena-pro-core-nginx"
DEFAULT_NGINX_IMAGE = "nginx:1.27-alpine"
DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = "18080"
DEFAULT_DASHBOARD_UPSTREAM_HOST = "host.docker.internal"
NGINX_CONFIG_VERSION = "1"
LABEL_NGINX_CONFIG_VERSION = f"{LABEL_PREFIX}.nginx-config-version"


@dataclass(frozen=True)
class NginxRoute:
    site: str
    exp_hash: str
    hostname: str
    container_name: str
    upstream_port: int


def docker_network_name() -> str:
    return os.environ.get(NETWORK_ENV_VAR, DEFAULT_NETWORK)


def nginx_container_name() -> str:
    return os.environ.get(NGINX_CONTAINER_ENV_VAR, DEFAULT_NGINX_CONTAINER)


def nginx_image() -> str:
    return os.environ.get(NGINX_IMAGE_ENV_VAR, DEFAULT_NGINX_IMAGE)


def nginx_config_directory() -> Path:
    """Keep the deployed default mount, isolate explicitly named proxies."""
    root = Path(tempfile.gettempdir()) / "webarena-pro-core-nginx"
    name = nginx_container_name()
    if name == DEFAULT_NGINX_CONTAINER:
        return root
    # Hash the identity used by the proxy lock, including names with path
    # separators, without changing the mount of an existing default proxy.
    suffix = hashlib.sha256(name.encode()).hexdigest()[:16]
    return root.with_name(f"{root.name}-{suffix}")


def dashboard_listen_host() -> str:
    return os.environ.get(DASHBOARD_HOST_ENV_VAR, DEFAULT_DASHBOARD_HOST)


def dashboard_listen_port() -> int:
    return int(os.environ.get(DASHBOARD_PORT_ENV_VAR, DEFAULT_DASHBOARD_PORT))


def dashboard_upstream_url(
    *,
    host: str | None = None,
    port: int | None = None,
) -> str:
    upstream_host = os.environ.get(
        DASHBOARD_UPSTREAM_HOST_ENV_VAR,
        DEFAULT_DASHBOARD_UPSTREAM_HOST,
    )
    resolved_host = upstream_host if host is None else host
    resolved_port = dashboard_listen_port() if port is None else int(port)
    return f"http://{resolved_host}:{resolved_port}"


def active_dashboard_upstream() -> str | None:
    host = dashboard_listen_host()
    port = dashboard_listen_port()
    try:
        with socket.create_connection((host, port), timeout=0.1):
            pass
    except OSError:
        return None
    return dashboard_upstream_url(port=port)


class NginxProxyManager:
    def __init__(self) -> None:
        self.client = docker.from_env(timeout=docker_timeout())

    def ensure_network(self) -> None:
        with runtime_lock(f"network:{docker_network_name()}"), docker_lifecycle_slot():
            try:
                self.client.networks.get(docker_network_name())
            except NotFound:
                try:
                    self.client.networks.create(docker_network_name(), driver="bridge")
                except APIError as error:
                    if error.status_code != 409:
                        raise
                    # Another process/client may have created it after inspection.
                    self.client.networks.get(docker_network_name())

    def ensure_proxy(
        self,
        *,
        dashboard_upstream: str | None = None,
        log: Callable[[str], None] | None = None,
    ) -> None:
        # All callers (including CLI/dashboard) share this lock. Holding the
        # permit only here keeps application readiness waits outside the pool.
        with runtime_lock(f"proxy:{nginx_container_name()}"):
            self.ensure_network()
            with docker_lifecycle_slot():
                _retry_lifecycle(
                    lambda: self._ensure_proxy_once(dashboard_upstream=dashboard_upstream, log=log),
                    action="refresh nginx proxy", name=nginx_container_name(),
                )

    def _ensure_proxy_once(
        self, *, dashboard_upstream: str | None, log: Callable[[str], None] | None,
    ) -> None:
        if log is None:
            log = lambda msg: None

        routes = self.discover_routes()
        if dashboard_upstream is None:
            dashboard_upstream = active_dashboard_upstream()
        config_path = self.write_config(routes, dashboard_upstream=dashboard_upstream)
        config_dir = config_path.parent
        container_name = nginx_container_name()
        image = nginx_image()
        host = web_server_bind_host()
        listen_port = web_server_port()

        mounts = [
            Mount(
                target="/etc/nginx/conf.d",
                source=str(config_dir),
                type="bind",
                read_only=True,
            ),
        ]
        ports = {"80/tcp": (host, listen_port)}
        labels = {
            LABEL_MANAGED: "nginx",
            LABEL_NGINX_CONFIG_VERSION: NGINX_CONFIG_VERSION,
        }

        container = None
        try:
            container = self.client.containers.get(container_name)
        except NotFound:
            pass

        if container is not None:
            if not self._nginx_container_matches(
                container,
                host=host,
                listen_port=listen_port,
                config_dir=config_dir,
            ):
                log("nginx settings changed, recreating reverse proxy container ...")
                try:
                    container.remove(force=True, v=True)
                except NotFound:
                    pass
                container = None

        if container is not None:
            if container.status != "running":
                container.start()
            self._reload(container)
            log(f"nginx reverse proxy reloaded with {len(routes)} route(s).")
            return

        try:
            self.client.images.get(image)
        except docker.errors.ImageNotFound:
            log(f"nginx image '{image}' not found locally, pulling ...")
            self.client.images.pull(image)

        container = self.client.containers.run(
            image=image,
            name=container_name,
            detach=True,
            network=docker_network_name(),
            ports=ports,
            mounts=mounts,
            labels=labels,
            extra_hosts={"host.docker.internal": "host-gateway"},
        )
        self._reload(container)
        log(f"nginx reverse proxy started with {len(routes)} route(s).")

    @staticmethod
    def _reload(container) -> None:
        # `-s reload` can return success before the master parses its config.
        # Validate syntax first. Website DNS is resolved at request time, so a
        # reset between this check and the master parsing cannot reject reload.
        for command in ("nginx -t", "nginx -s reload"):
            result = container.exec_run(command)
            exit_code = result.exit_code if hasattr(result, "exit_code") else result[0]
            if exit_code == 0:
                continue
            output = result.output if hasattr(result, "output") else result[1]
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            message = f"{command} failed in {container.name}: {output}"
            details = str(output).lower()
            if "host not found in upstream" in details or (
                "nginx.pid" in details and any(marker in details for marker in (
                    "invalid pid number", "no such file or directory",
                ))
            ):
                # Re-discover routes and rewrite config on the next attempt.
                raise _LifecyclePending(message)
            raise RuntimeError(message)

    def stop_proxy(self, *, log: Callable[[str], None] | None = None) -> bool:
        if log is None:
            log = lambda msg: None

        with runtime_lock(f"proxy:{nginx_container_name()}"), docker_lifecycle_slot():
            try:
                container = self.client.containers.get(nginx_container_name())
            except NotFound:
                return False
            DockerContainerManager._remove_container(container)
            log("nginx reverse proxy stopped.")
            return True

    def discover_routes(self) -> list[NginxRoute]:
        routes_by_host: dict[str, NginxRoute] = {}
        for container in self.client.containers.list(
            filters={"label": f"{LABEL_MANAGED}=website"}, ignore_removed=True
        ):
            try:
                container.reload()
            except NotFound:
                # Another worker may remove the container while resetting its task.
                continue
            attrs = container.attrs or {}
            state = attrs.get("State") or {}
            if (
                not state.get("Running") or state.get("Paused") or state.get("Restarting")
                or state.get("Status", "running") != "running"
            ):
                continue
            network = (attrs.get("NetworkSettings", {}).get("Networks") or {}).get(
                docker_network_name()
            ) or {}
            if not network.get("EndpointID") or not (
                network.get("IPAddress") or network.get("GlobalIPv6Address")
            ):
                continue
            labels = attrs.get("Config", {}).get("Labels", {}) or {}
            site = labels.get(LABEL_SITE)
            exp_hash = labels.get(LABEL_EXP_HASH)
            upstream_port = labels.get(LABEL_UPSTREAM_PORT)
            if not site or not exp_hash or not upstream_port:
                continue
            hostname = website_hostname(str(site), exp_hash=str(exp_hash))
            route = NginxRoute(
                site=str(site),
                exp_hash=str(exp_hash),
                hostname=hostname,
                container_name=container.name,
                upstream_port=int(upstream_port),
            )
            existing = routes_by_host.get(route.hostname)
            if existing is None or route.container_name > existing.container_name:
                routes_by_host[route.hostname] = route

        routes = list(routes_by_host.values())
        routes.sort(key=lambda route: route.hostname)
        return routes

    def write_config(
        self,
        routes: list[NginxRoute],
        *,
        dashboard_upstream: str | None = None,
    ) -> Path:
        config_dir = nginx_config_directory()
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "default.conf"
        temp_path = config_dir / ".default.conf.tmp"
        temp_path.write_text(
            render_nginx_config(routes, dashboard_upstream=dashboard_upstream),
            encoding="utf-8",
        )
        temp_path.replace(config_path)
        return config_path

    def _nginx_container_matches(
        self,
        container,
        *,
        host: str,
        listen_port: int,
        config_dir: Path,
    ) -> bool:
        container.reload()
        attrs = container.attrs or {}
        labels = attrs.get("Config", {}).get("Labels", {}) or {}
        if str(labels.get(LABEL_NGINX_CONFIG_VERSION)) != NGINX_CONFIG_VERSION:
            return False

        ports = attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
        bindings = ports.get("80/tcp")
        if not isinstance(bindings, list) or not bindings:
            return False
        binding = bindings[0]
        ports_match = str(binding.get("HostIp") or host) in {host, "0.0.0.0"} and str(
            binding.get("HostPort")
        ) == str(listen_port)
        if not ports_match:
            return False

        networks = attrs.get("NetworkSettings", {}).get("Networks", {}) or {}
        if docker_network_name() not in networks:
            return False

        expected_config_source = os.path.realpath(str(config_dir))
        mounts = attrs.get("Mounts", []) or []
        return any(
            mount.get("Destination") == "/etc/nginx/conf.d"
            and os.path.realpath(str(mount.get("Source", ""))) == expected_config_source
            for mount in mounts
        )


def render_nginx_config(
    routes: list[NginxRoute],
    *,
    dashboard_upstream: str | None = None,
) -> str:
    dashboard_locations = _render_dashboard_server(dashboard_upstream)
    route_servers = "\n".join(_render_route_server(route) for route in routes)
    return f"""server_names_hash_bucket_size 128;

map $http_upgrade $webarena_connection_upgrade {{
    default upgrade;
    '' close;
}}

server {{
    listen 80 default_server;
    server_name _;
    return 404 "Unknown WebArena-Pro environment host\\n";
}}

{dashboard_locations}

{route_servers}
"""


def _render_dashboard_server(dashboard_upstream: str | None) -> str:
    hostname = dashboard_hostname()
    if dashboard_upstream is None:
        body = """    location / {
        default_type text/plain;
        return 503 "Run webarena-pro serve to enable the dashboard.\\n";
    }"""
    else:
        body = _render_proxy_location(dashboard_upstream)
    return f"""server {{
    listen 80;
    server_name {hostname};
    client_max_body_size 0;

{body}
}}"""


def _render_route_server(route: NginxRoute) -> str:
    upstream = f"http://{route.container_name}:{route.upstream_port}"
    return f"""server {{
    listen 80;
    server_name {route.hostname};
    client_max_body_size 0;

{_render_proxy_location(upstream, resolve_container=True)}
}}"""


def _render_proxy_location(upstream: str, *, resolve_container: bool = False) -> str:
    if resolve_container:
        # Docker's embedded DNS resolves names on the user-defined network.
        # A variable defers resolution until the request; no URI suffix keeps
        # the original path/query behavior of the literal proxy_pass above.
        proxy_target = f"""resolver 127.0.0.11 valid=5s;
        resolver_timeout 5s;
        set $webarena_upstream {upstream};
        proxy_pass $webarena_upstream;"""
    else:
        proxy_target = f"proxy_pass {upstream};"
    return f"""    location / {{
        {proxy_target}
        proxy_http_version 1.1;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $http_host;
        proxy_set_header X-Forwarded-Port {web_server_port()};
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $webarena_connection_upgrade;
        proxy_redirect off;
    }}"""


def public_dashboard_url() -> str:
    return build_dashboard_url()
