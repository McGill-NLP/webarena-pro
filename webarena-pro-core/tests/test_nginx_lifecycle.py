import multiprocessing
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from docker.errors import APIError, NotFound
from requests import Response

from webarena_pro_core.nginx import (
    DEFAULT_NGINX_CONTAINER,
    NginxProxyManager,
    NginxRoute,
    docker_network_name,
    nginx_config_directory,
)
from webarena_pro_core.runtime_locks import runtime_lock


def _write_config_concurrently(root, name, barrier):
    import webarena_pro_core.nginx as nginx

    os.environ["WP_NGINX_CONTAINER_NAME"] = name
    os.environ["WP_RUNTIME_LOCK_DIR"] = str(Path(root) / "locks")
    nginx.tempfile.gettempdir = lambda: root
    original_replace = Path.replace

    def replace_after_both_files_written(path, target):
        barrier.wait(10)
        return original_replace(path, target)

    Path.replace = replace_after_both_files_written
    manager = NginxProxyManager.__new__(NginxProxyManager)
    route = NginxRoute("nextcloud", name, f"{name}.localhost", f"{name}-upstream", 80)
    with runtime_lock(f"proxy:{name}"):
        path = manager.write_config([route])
        assert f"server_name {name}.localhost;" in path.read_text()


def test_custom_proxies_write_independent_configs_concurrently(monkeypatch, tmp_path):
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    names = ["proxy-one", "proxy-two"]
    workers = [
        context.Process(target=_write_config_concurrently, args=(str(tmp_path), name, barrier))
        for name in names
    ]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(15)
            assert worker.exitcode == 0
        monkeypatch.setattr("webarena_pro_core.nginx.tempfile.gettempdir", lambda: str(tmp_path))
        for name in names:
            monkeypatch.setenv("WP_NGINX_CONTAINER_NAME", name)
            config = (nginx_config_directory() / "default.conf").read_text()
            assert f"server_name {name}.localhost;" in config
            assert all(f"server_name {other}.localhost;" not in config for other in names if other != name)
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
            worker.join(5)


def test_default_proxy_keeps_existing_mount_directory(monkeypatch, tmp_path):
    monkeypatch.setattr("webarena_pro_core.nginx.tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("WP_NGINX_CONTAINER_NAME", DEFAULT_NGINX_CONTAINER)
    assert nginx_config_directory() == tmp_path / "webarena-pro-core-nginx"


@pytest.fixture
def proxy(monkeypatch, tmp_path):
    monkeypatch.setenv("WP_RUNTIME_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setattr("webarena_pro_core.docker.time.sleep", lambda _: None)
    monkeypatch.setattr("webarena_pro_core.nginx.active_dashboard_upstream", lambda: None)
    manager = NginxProxyManager.__new__(NginxProxyManager)
    manager.client = Mock()
    manager.discover_routes = Mock(return_value=[])
    manager.write_config = Mock(return_value=tmp_path / "default.conf")
    manager._nginx_container_matches = Mock(return_value=True)
    container = manager.client.containers.get.return_value
    container.name, container.status = "proxy", "running"
    container.exec_run.return_value = SimpleNamespace(exit_code=0, output=b"")
    return manager, container


def test_reload_rediscovers_routes_after_upstream_disappears(proxy):
    manager, container = proxy
    active = NginxRoute("nextcloud", "w1", "nextcloud--w1.localhost", "nextcloud-w1", 80)
    removed = NginxRoute("nextcloud", "w2", "nextcloud--w2.localhost", "nextcloud-w2", 80)
    manager.discover_routes.side_effect = [[active, removed], [active]]
    container.exec_run.side_effect = [
        SimpleNamespace(exit_code=1, output=b'host not found in upstream "nextcloud-w2"'),
        SimpleNamespace(exit_code=0, output=b""),
        SimpleNamespace(exit_code=0, output=b""),
    ]

    manager.ensure_proxy()

    assert manager.discover_routes.call_count == 2
    assert manager.write_config.call_args_list == [
        call([active, removed], dashboard_upstream=None),
        call([active], dashboard_upstream=None),
    ]
    assert container.exec_run.call_args_list == [
        call("nginx -t"), call("nginx -t"), call("nginx -s reload"),
    ]


def test_proxy_recreation_removes_attached_anonymous_volumes(proxy):
    manager, container = proxy
    manager._nginx_container_matches.return_value = False
    manager.client.containers.run.return_value.exec_run.return_value = SimpleNamespace(
        exit_code=0, output=b"",
    )

    manager.ensure_proxy()

    container.remove.assert_called_once_with(force=True, v=True)
    mounts = manager.client.containers.run.call_args.kwargs["mounts"]
    assert mounts[0]["Type"] == "bind"
    assert mounts[0]["ReadOnly"] is True
    assert manager.client.volumes.mock_calls == []


def test_reload_retries_proxy_disappearing_after_inspection(proxy):
    manager, container = proxy
    manager._nginx_container_matches.side_effect = [NotFound("container replaced"), True]
    manager.ensure_proxy()
    assert manager.discover_routes.call_count == 2
    assert container.exec_run.call_args_list == [call("nginx -t"), call("nginx -s reload")]


def test_reload_does_not_retry_persistent_configuration_errors(proxy):
    manager, container = proxy
    container.exec_run.return_value = SimpleNamespace(exit_code=1, output=b'unknown directive "invalid"')
    with pytest.raises(RuntimeError, match="nginx -t.*unknown directive"):
        manager.ensure_proxy()
    assert manager.discover_routes.call_count == 1
    container.exec_run.assert_called_once_with("nginx -t")


def test_reload_exhaustion_reports_last_failure(proxy, monkeypatch):
    manager, container = proxy
    monkeypatch.setattr("webarena_pro_core.docker.LIFECYCLE_ATTEMPTS", 3)
    container.exec_run.return_value = SimpleNamespace(exit_code=1, output=b"host not found in upstream")
    with pytest.raises(RuntimeError, match="refresh nginx proxy.*3 attempts.*host not found"):
        manager.ensure_proxy()
    assert manager.discover_routes.call_count == 3


def test_network_create_race_rechecks_that_network_exists(proxy):
    manager, _ = proxy
    response = Response()
    response.status_code = 409
    manager.client.networks.get.side_effect = [NotFound("absent"), Mock()]
    manager.client.networks.create.side_effect = APIError("already exists", response=response)
    manager.ensure_network()
    assert manager.client.networks.get.call_args_list == [
        call(docker_network_name()), call(docker_network_name()),
    ]
