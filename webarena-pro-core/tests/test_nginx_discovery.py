from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from docker.errors import APIError, NotFound
from docker.models.containers import ContainerCollection

from webarena_pro_core import (
    LABEL_EXP_HASH,
    LABEL_MANAGED,
    LABEL_SITE,
    LABEL_UPSTREAM_PORT,
    website_hostname,
)
from webarena_pro_core.nginx import NginxProxyManager, NginxRoute, docker_network_name


def make_manager(monkeypatch, *, error, fail_on_inspection):
    api = Mock()
    api.containers.return_value = [
        {"Id": name} for name in ("nextcloud", "removed", "mattermost")
    ]
    inspections = {}

    def inspect_container(container_id):
        inspections[container_id] = inspections.get(container_id, 0) + 1
        if container_id == "removed" and inspections[container_id] == fail_on_inspection:
            raise error
        return {
            "Id": container_id,
            "Name": f"/{container_id}",
            "State": {"Running": True, "Status": "running"},
            "NetworkSettings": {"Networks": {docker_network_name(): {
                "EndpointID": f"endpoint-{container_id}", "IPAddress": "172.20.0.2",
            }}},
            "Config": {
                "Labels": {
                    LABEL_MANAGED: "website",
                    LABEL_SITE: container_id,
                    LABEL_EXP_HASH: "worker-1",
                    LABEL_UPSTREAM_PORT: "80",
                }
            },
        }

    api.inspect_container.side_effect = inspect_container
    client = SimpleNamespace(api=api)
    # Exercise the SDK's real list/get/reload behavior without a Docker daemon.
    client.containers = ContainerCollection(client)
    monkeypatch.setattr("webarena_pro_core.nginx.docker.from_env", lambda **kwargs: client)
    return NginxProxyManager()


@pytest.mark.parametrize("fail_on_inspection", [1, 2], ids=["list", "reload"])
def test_discovery_skips_removed_containers(monkeypatch, fail_on_inspection):
    manager = make_manager(
        monkeypatch,
        error=NotFound("container removed during reset"),
        fail_on_inspection=fail_on_inspection,
    )

    assert manager.discover_routes() == [
        NginxRoute(
            site=site,
            exp_hash="worker-1",
            hostname=website_hostname(site, exp_hash="worker-1"),
            container_name=site,
            upstream_port=80,
        )
        for site in ("mattermost", "nextcloud")
    ]
    assert manager.client.api.containers.call_args.kwargs["filters"] == {
        "label": f"{LABEL_MANAGED}=website"
    }


@pytest.mark.parametrize("fail_on_inspection", [1, 2], ids=["list", "reload"])
def test_discovery_propagates_unexpected_inspection_errors(monkeypatch, fail_on_inspection):
    error = APIError("Docker daemon failed")
    manager = make_manager(
        monkeypatch, error=error, fail_on_inspection=fail_on_inspection
    )

    with pytest.raises(APIError) as caught:
        manager.discover_routes()

    assert caught.value is error


def test_discovery_propagates_container_listing_errors(monkeypatch):
    error = APIError("Docker daemon failed")
    manager = make_manager(monkeypatch, error=None, fail_on_inspection=0)
    manager.client.api.containers.side_effect = error

    with pytest.raises(APIError) as caught:
        manager.discover_routes()

    assert caught.value is error


@pytest.mark.parametrize("change", [
    "stopped", "paused", "restarting", "removing", "detached", "empty-endpoint", "empty-address",
])
def test_discovery_excludes_routes_that_became_unusable(monkeypatch, change):
    manager = make_manager(monkeypatch, error=None, fail_on_inspection=0)
    inspect = manager.client.api.inspect_container.side_effect

    def inspect_changed(container_id):
        attrs = inspect(container_id)
        if container_id == "removed":
            state = attrs["State"]
            networks = attrs["NetworkSettings"]["Networks"]
            if change == "stopped":
                state.update(Running=False, Status="exited")
            elif change == "paused":
                state["Paused"] = True
            elif change == "restarting":
                state["Restarting"] = True
            elif change == "removing":
                state["Status"] = "removing"
            elif change == "detached":
                networks.clear()
            elif change == "empty-endpoint":
                networks[docker_network_name()]["EndpointID"] = ""
            else:
                networks[docker_network_name()]["IPAddress"] = ""
        return attrs

    manager.client.api.inspect_container.side_effect = inspect_changed
    assert [route.site for route in manager.discover_routes()] == ["mattermost", "nextcloud"]
