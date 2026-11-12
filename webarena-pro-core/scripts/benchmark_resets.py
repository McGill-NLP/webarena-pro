#!/usr/bin/env python3
"""Measure local images using isolated, disposable website containers.

Run with the core package installed. Images must already be local; pulls and
builds are excluded. No existing website container is stopped or reset.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import time
import uuid

SITES = (
    "nextcloud", "erp-next", "password-manager", "flight-search", "firefly",
    "travelmap", "jobportal", "thunderbird", "mattermost", "immich", "metabase",
    "mydrive", "notion", "yt-lite", "x-lite", "minerva-lite", "acidwave",
    "peppermint", "penpot", "pipedrive",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sites", nargs="*", choices=(*SITES, "all"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", action="append", default=[], metavar="SITE=IMAGE")
    parser.add_argument("--port-base", type=int, default=45000)
    parser.add_argument("--resets", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    selected = list(SITES) if not args.sites or args.sites == ["all"] else args.sites
    if "all" in selected or len(selected) != len(set(selected)):
        parser.error("Select all by itself, or distinct site names")
    if args.resets < 1 or args.timeout < 1 or not 1024 <= args.port_base <= 65000:
        parser.error("Use positive resets/timeout and a port base between 1024 and 65000")
    overrides = {}
    for assignment in args.image:
        site, separator, reference = assignment.partition("=")
        if not separator or site not in SITES or not reference:
            parser.error("--image must be SITE=IMAGE")
        overrides[site] = reference

    # Do this before importing core: several URL/port settings are cached at import.
    for key in list(os.environ):
        if key.startswith("WP_"):
            del os.environ[key]
    namespace = "reset-audit-" + uuid.uuid4().hex[:12]
    os.environ.update(WP_URL_MODE="port", WP_EXP_HASH=namespace, WP_RESET_BACKEND="auto")
    for index, site in enumerate(SITES):
        key = site.upper().replace("-", "_")
        os.environ[f"WP_{key}_HOST_PORT"] = str(args.port_base + index * 10)
        os.environ[f"WP_{key}_CONTAINER_NAME"] = f"{namespace}-{site}"
    os.environ["WP_PEPPERMINT_API_HOST_PORT"] = str(args.port_base + 200)

    import docker
    from webarena_pro_core import WEBSITES_IMAGES, build_website_ports
    from webarena_pro_core import state_reset as reset
    from webarena_pro_core.docker import DockerContainerManager

    WEBSITES_IMAGES.update(overrides)
    reset.READINESS_TIMEOUT_SECONDS = args.timeout
    reset.SITE_READINESS_TIMEOUT_SECONDS = {site: args.timeout for site in SITES}
    reset.RESET_SNAPSHOT_TIMEOUT_SECONDS = args.timeout
    reset.SITE_RESET_SNAPSHOT_TIMEOUT_SECONDS = {site: args.timeout for site in SITES}
    client = docker.from_env(timeout=args.timeout)
    owned_names = {f"{namespace}-{site}" for site in selected}

    class AuditManager(DockerContainerManager):
        def reset_container(self, **kwargs):
            if kwargs["name"] not in owned_names:
                raise RuntimeError("Refusing to modify a container outside this audit")
            try:
                existing = client.containers.get(kwargs["name"])
            except docker.errors.NotFound:
                pass
            else:
                if existing.labels.get("webarena-pro.audit") != namespace:
                    raise RuntimeError("Refusing to replace an existing container")
            kwargs["labels"] = {**kwargs.get("labels", {}), "webarena-pro.audit": namespace}
            kwargs["remove_port_conflicts"] = False
            kwargs["ports"] = {
                port: ("127.0.0.1", host_port)
                for port, host_port in (kwargs.get("ports") or {}).items()
            }
            return super().reset_container(**kwargs)

    def deadline(_signal, _frame):
        raise TimeoutError("Audit phase exceeded its time limit")

    signal.signal(signal.SIGALRM, deadline)
    manager = AuditManager()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error("Output already exists; use a new report path")
    failures = 0
    for site in selected:
        name = f"{namespace}-{site}"
        row = {"site": site, "image": WEBSITES_IMAGES[site], "measurements": {}}
        try:
            image = client.images.get(row["image"])
            row.update(image_id=image.id, image_created=image.attrs["Created"])
            for port in build_website_ports(site).values():
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", int(port)))
            phases = ["start", *(f"reset_{i + 1}" for i in range(args.resets)), "restart"]
            for phase in phases:
                print(json.dumps({"site": site, "phase": phase, "event": "begin"}), flush=True)
                started = time.monotonic()
                signal.alarm(args.timeout * 2)
                try:
                    if phase == "restart":
                        client.containers.get(name).restart(timeout=10)
                        reset.wait_until_site_ready(site)
                    else:
                        reset.reset_site(site, container_manager=manager)
                    result = round(time.monotonic() - started, 3)
                except Exception as error:
                    failures += 1
                    result = {"elapsed": round(time.monotonic() - started, 3), "error": str(error)}
                finally:
                    signal.alarm(0)
                row["measurements"][phase] = result
                print(json.dumps({"site": site, "phase": phase, "result": result}), flush=True)
                if phase == "start" and isinstance(result, dict):
                    break
        except Exception as error:
            failures += 1
            row["error"] = str(error)
        finally:
            try:
                container = client.containers.get(name)
                if container.labels.get("webarena-pro.audit") == namespace:
                    container.remove(force=True, v=True)
            except docker.errors.NotFound:
                pass
            with args.output.open("a") as output:
                output.write(json.dumps(row) + "\n")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
