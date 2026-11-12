from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlparse

from docker.errors import NotFound

from . import (
    WEB_SERVER_PORT_ENV_VAR,
    WEBSITES_CONTAINER_PORTS,
    WEBSITES_HOST_PORT_ENV_VARS,
    WEBSITES_HOST_PORTS,
    WEBSITES_IMAGES,
    active_exp_hash,
    build_dashboard_url,
    build_website_url,
    website_published_ports,
    container_name_for_site,
    labels_for_site,
    uses_subdomain_urls,
    website_environment,
)
from .config import get_website_credentials
from .docker import DockerContainerManager
from .nginx import (
    NginxProxyManager,
    dashboard_listen_port,
    dashboard_upstream_url,
    docker_network_name,
)

_DASHBOARD_HTML_PATH = Path(__file__).parent / "static" / "index.html"


def _load_dashboard_html() -> str:
    try:
        return _DASHBOARD_HTML_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        package_static = files("webarena_pro_core").joinpath("static/index.html")
        return package_static.read_text(encoding="utf-8")


def _resolve_container_port(name: str) -> int:
    return int(WEBSITES_CONTAINER_PORTS.get(name, 80))


def _resolve_host_port(name: str) -> int:
    return int(WEBSITES_HOST_PORTS[name])


def _build_ports(name: str) -> dict[str, int] | None:
    return website_published_ports(
        name, host_port=_resolve_host_port(name), use_proxy=uses_subdomain_urls()
    )


def _network_name() -> str | None:
    return docker_network_name() if uses_subdomain_urls() else None


def _preferred_ports(name: str) -> list[str]:
    ports = [str(_resolve_container_port(name)), "80"]
    deduplicated: list[str] = []
    for port in ports:
        if port not in deduplicated:
            deduplicated.append(port)
    return deduplicated


def _collect_environments(manager: DockerContainerManager) -> list[dict[str, str | bool | None]]:
    environments: list[dict[str, str | bool | None]] = []

    for name, image in WEBSITES_IMAGES.items():
        entry: dict[str, str | bool | None] = {
            "name": str(name),
            "image": str(image),
            "status": "not-created",
            "health": "unknown",
            "url": None,
            "running": False,
            "host_port": WEBSITES_HOST_PORTS.get(name),
            "host_port_env_var": WEBSITES_HOST_PORT_ENV_VARS.get(name),
            "credentials": get_website_credentials(str(name)),
        }
        try:
            container_name = container_name_for_site(str(name))
            info = manager.get_container_info(container_name)
            entry["status"] = info.status
            entry["health"] = info.health
            entry["running"] = info.status == "running"
            entry["url"] = (
                build_website_url(str(name), host_port=_resolve_host_port(str(name)))
                if uses_subdomain_urls()
                else manager.get_container_url(
                    name=container_name,
                    preferred_container_ports=_preferred_ports(str(name)),
                )
            )
        except NotFound:
            pass
        except Exception as error:  # pragma: no cover - defensive API reporting
            entry["status"] = "error"
            entry["health"] = str(error)
        environments.append(entry)

    return environments


class DashboardRequestHandler(BaseHTTPRequestHandler):
    manager: DockerContainerManager

    def _proxy(self) -> NginxProxyManager | None:
        return getattr(self.server, "proxy", None)  # type: ignore[attr-defined]

    def _send_json(self, payload: dict | list, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = html.encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _split_api_path(self, path: str) -> list[str]:
        return [part for part in path.strip("/").split("/") if part]

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            try:
                html = _load_dashboard_html()
            except FileNotFoundError:
                self._send_json(
                    {
                        "error": (
                            "Dashboard static asset is missing (static/index.html). "
                            "Reinstall webarena-pro-core after updating package metadata."
                        )
                    },
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            self._send_html(html)
            return

        if parsed.path == "/api/environments":
            environments = _collect_environments(self.manager)
            self._send_json({"environments": environments})
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        parts = self._split_api_path(parsed.path)

        if len(parts) != 4 or parts[:2] != ["api", "environments"]:
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return

        name = parts[2]
        action = parts[3]

        if name not in WEBSITES_IMAGES:
            self._send_json(
                {"error": f"Unknown environment '{name}'."},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            image = WEBSITES_IMAGES[name]
            container_name = container_name_for_site(name)
            proxy = self._proxy()
            if proxy is not None:
                proxy.ensure_network()

            if action == "start":
                self.manager.ensure_container_running(
                    name=container_name,
                    image=image,
                    environment=website_environment(name, exp_hash=active_exp_hash()),
                    ports=_build_ports(name),
                    labels=labels_for_site(name, exp_hash=active_exp_hash()),
                    network=_network_name(),
                    log=lambda msg, _name=name: print(f"[{_name}] {msg}", flush=True),
                )
            elif action == "restart":
                self.manager.reset_container(
                    name=container_name,
                    image=image,
                    environment=website_environment(name, exp_hash=active_exp_hash()),
                    ports=_build_ports(name),
                    labels=labels_for_site(name, exp_hash=active_exp_hash()),
                    network=_network_name(),
                    log=lambda msg, _name=name: print(f"[{_name}] {msg}", flush=True),
                )
            elif action == "stop":
                self.manager.stop_container(container_name)
            else:
                self._send_json(
                    {"error": f"Unsupported action '{action}'."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
        except ValueError as error:
            self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return
        except Exception as error:  # pragma: no cover - runtime docker errors
            self._send_json({"error": str(error)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        proxy = self._proxy()
        if proxy is not None:
            proxy.ensure_proxy(dashboard_upstream=dashboard_upstream_url())
        environments = _collect_environments(self.manager)
        self._send_json({"environments": environments}, status=HTTPStatus.OK)


def start_dashboard_server(*, host: str = "127.0.0.1", port: int = 8080) -> None:
    # Importing configuration helpers must not require a running Docker daemon.
    DashboardRequestHandler.manager = DockerContainerManager()
    if not uses_subdomain_urls():
        server = ThreadingHTTPServer((host, port), DashboardRequestHandler)
        server.proxy = None  # type: ignore[attr-defined]
        print(f"Dashboard available at http://{host}:{port}")
        print("Press Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping dashboard...")
        finally:
            server.server_close()
        return

    os.environ[WEB_SERVER_PORT_ENV_VAR] = str(port)
    upstream_port = dashboard_listen_port()
    server = ThreadingHTTPServer((host, upstream_port), DashboardRequestHandler)
    proxy = NginxProxyManager()
    server.proxy = proxy  # type: ignore[attr-defined]
    proxy.ensure_proxy(dashboard_upstream=dashboard_upstream_url(port=upstream_port))
    print(f"Dashboard available at {build_dashboard_url()}")
    print(f"Dashboard upstream listening at http://{host}:{upstream_port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard...")
    finally:
        server.server_close()
