from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from docker.errors import APIError, ImageNotFound, NotFound
from requests import Response
from requests.exceptions import ReadTimeout

from webarena_pro_core.docker import DockerContainerManager
from webarena_pro_core.nginx import NginxProxyManager
from webarena_pro_core import state_reset


def conflict(message):
    response = Response()
    response.status_code = 409
    return APIError(message, response=response, explanation=message)


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("WP_RUNTIME_LOCK_DIR", str(tmp_path))
    monkeypatch.setenv("WP_DOCKER_LIFECYCLE_SLOTS", "1")
    monkeypatch.setenv("WP_DOCKER_LOCK_TIMEOUT_SECONDS", "0.1")
    monkeypatch.setattr("webarena_pro_core.docker.time.sleep", lambda _: None)


def manager_with_container():
    manager = DockerContainerManager.__new__(DockerContainerManager)
    manager.client = Mock()
    manager.client.images.get.return_value = SimpleNamespace(id="image-id")
    container = Mock()
    container.name = "site-worker"
    container.status = "running"
    container.attrs = {"Image": "image-id", "State": {"Running": True}}
    manager.client.containers.get.return_value = container
    manager.client.containers.run.return_value = container
    return manager, container


@pytest.mark.parametrize("failure", [
    ReadTimeout("read timed out"), conflict('container name is already in use'),
])
def test_create_reconciles_success_after_timeout_or_name_race(failure):
    manager, container = manager_with_container()
    manager.client.containers.get.side_effect = [NotFound("absent"), container]
    manager.client.containers.run.side_effect = failure
    hook = Mock()

    result = manager.ensure_container_running(name=container.name, image="image", post_start=hook)

    assert result.status == "running"
    manager.client.containers.run.assert_called_once()
    container.remove.assert_not_called()
    hook.assert_called_once_with(container)


def test_start_reconciles_success_after_timeout():
    manager, container = manager_with_container()
    container.status = "exited"

    def start():
        container.status = "running"
        raise ReadTimeout("read timed out")

    container.start.side_effect = start
    assert manager.ensure_container_running(name=container.name, image="image").status == "running"
    container.start.assert_called_once()


@pytest.mark.parametrize("failure", [
    NotFound("already removed"), ReadTimeout("read timed out"),
    conflict("removal of container is already in progress"),
])
def test_remove_tolerates_absence_or_inflight_removal(failure):
    manager, container = manager_with_container()
    container.remove.side_effect = [failure, NotFound("gone")]
    manager.stop_container(container.name)
    # Retrying by the name here could accidentally delete a new replacement.
    manager.client.containers.get.assert_called_once_with(container.name)
    expected_attempts = 1 if isinstance(failure, NotFound) else 2
    assert container.remove.call_args_list == [call(force=True, v=True)] * expected_attempts


def test_stop_removes_attached_anonymous_volumes_without_global_pruning():
    manager, container = manager_with_container()

    manager.stop_container(container.name)

    container.remove.assert_called_once_with(force=True, v=True)
    assert manager.client.volumes.mock_calls == []


def test_outdated_container_replacement_removes_attached_anonymous_volumes():
    manager, old = manager_with_container()
    old.attrs["Image"] = "old-image-id"
    new = Mock()
    new.name, new.status, new.attrs = old.name, "running", {"State": {}}
    manager.client.containers.run.return_value = new
    volumes = {
        "persisted-data": {"bind": "/data", "mode": "rw"},
        "/tmp/seed": {"bind": "/seed", "mode": "ro"},
    }

    manager.ensure_container_running(name=old.name, image="image", volumes=volumes)

    old.remove.assert_called_once_with(force=True, v=True)
    assert manager.client.containers.run.call_args.kwargs["volumes"] == volumes
    assert manager.client.volumes.mock_calls == []


def test_reset_does_not_remove_new_container_after_create_timeout():
    manager, old = manager_with_container()
    new = Mock()
    new.name, new.status, new.attrs = old.name, "running", old.attrs
    manager.client.containers.get.side_effect = [old, NotFound("removed"), new]
    manager.client.containers.run.side_effect = ReadTimeout("created, response lost")

    result = manager.reset_container(name=old.name, image="image")

    assert result.status == "running"
    old.remove.assert_called_once_with(force=True, v=True)
    new.remove.assert_not_called()
    manager.client.containers.run.assert_called_once()


@pytest.mark.parametrize("message", ["volume is in use", "volume is already in use"])
def test_unrelated_conflict_is_not_retried(message):
    manager, container = manager_with_container()
    error = conflict(message)
    container.remove.side_effect = error
    with pytest.raises(APIError) as raised:
        manager.stop_container(container.name)
    assert raised.value is error
    container.remove.assert_called_once()


def test_port_conflict_cleanup_reports_persistent_removal_failure():
    manager, container = manager_with_container()
    manager.client.api.containers.return_value = [
        {"Id": "old-id", "Names": [f"/{container.name}"], "Ports": [{"PublicPort": 8080}]},
    ]
    container.attrs["NetworkSettings"] = {"Ports": {"80/tcp": [{"HostPort": "8080"}]}}
    container.remove.side_effect = APIError("permission denied")
    with pytest.raises(APIError, match="permission denied"):
        manager.remove_containers_using_host_ports(host_ports={8080})


def test_port_conflict_cleanup_removes_attached_anonymous_volumes():
    manager, container = manager_with_container()
    manager.client.api.containers.return_value = [
        {"Id": "old-id", "Names": [f"/{container.name}"], "Ports": [{"PublicPort": 8080}]},
    ]
    container.attrs["NetworkSettings"] = {"Ports": {"80/tcp": [{"HostPort": "8080"}]}}

    manager.remove_containers_using_host_ports(host_ports={8080})

    container.remove.assert_called_once_with(force=True, v=True)


def test_port_conflict_cleanup_does_not_delete_replacement_with_same_name():
    manager, replacement = manager_with_container()
    manager.client.api.containers.return_value = [
        {"Id": "old-id", "Names": [f"/{replacement.name}"], "Ports": [{"PublicPort": 8080}]},
    ]

    def inspect(identifier):
        if identifier == "old-id":
            raise NotFound("old container disappeared after listing")
        return replacement

    manager.client.containers.get.side_effect = inspect
    manager.remove_containers_using_host_ports(host_ports={8080})
    manager.client.containers.get.assert_called_once_with("old-id")
    replacement.remove.assert_not_called()


def test_port_conflict_cleanup_rechecks_current_bindings():
    manager, container = manager_with_container()
    manager.client.api.containers.return_value = [
        {"Id": "old-id", "Names": [f"/{container.name}"], "Ports": [{"PublicPort": 8080}]},
    ]
    container.attrs["NetworkSettings"] = {"Ports": {"80/tcp": None}}
    manager.remove_containers_using_host_ports(host_ports={8080})
    container.remove.assert_not_called()


def test_missing_image_is_not_retried_as_missing_container():
    manager, container = manager_with_container()
    manager.client.containers.get.side_effect = NotFound("container absent")
    manager.ensure_image_available = Mock(side_effect=ImageNotFound("registry image absent"))
    with pytest.raises(ImageNotFound):
        manager.ensure_container_running(name=container.name, image="image")
    manager.ensure_image_available.assert_called_once()


def test_exhaustion_reports_operation_and_container(monkeypatch):
    manager, container = manager_with_container()
    monkeypatch.setattr("webarena_pro_core.docker.LIFECYCLE_ATTEMPTS", 3)
    container.remove.side_effect = conflict("removal of container is already in progress")
    with pytest.raises(RuntimeError, match="remove.*site-worker.*3 attempts"):
        manager.stop_container(container.name)
    assert container.remove.call_count == 3


def test_post_start_failure_is_not_replayed():
    manager, container = manager_with_container()
    hook = Mock(side_effect=ReadTimeout("hook timed out"))
    with pytest.raises(ReadTimeout):
        manager.ensure_container_running(name=container.name, image="image", post_start=hook)
    hook.assert_called_once()


@pytest.mark.parametrize("timeout", [None, "123"])
def test_all_runtime_clients_use_configured_timeout(monkeypatch, timeout):
    if timeout is None:
        monkeypatch.delenv("WP_DOCKER_TIMEOUT_SECONDS", raising=False)
    else:
        monkeypatch.setenv("WP_DOCKER_TIMEOUT_SECONDS", timeout)
    factory = Mock()
    monkeypatch.setattr("docker.from_env", factory)
    DockerContainerManager()
    NginxProxyManager()
    state_reset._docker_client_from_env("nextcloud")
    assert factory.call_count == 3
    for call in factory.call_args_list:
        assert call.kwargs == {"timeout": 300 if timeout is None else 123}
