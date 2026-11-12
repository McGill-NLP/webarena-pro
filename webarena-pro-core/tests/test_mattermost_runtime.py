import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from webarena_pro_core import cli, dashboard_server, state_reset
from webarena_pro_core import website_environment, website_published_ports


def test_dashboard_import_does_not_connect_to_docker():
    subprocess.run(
        [sys.executable, "-c", """
from unittest.mock import patch
with patch('docker.from_env', side_effect=AssertionError('unexpected Docker connection')):
    from webarena_pro_core import dashboard_server
    assert dashboard_server._build_ports('mattermost')['8443/tcp'] == 8443
"""],
        check=True,
    )


@pytest.mark.parametrize("mode", ["subdomain", "port"])
def test_dashboard_start_initializes_manager_before_serving(monkeypatch, mode):
    monkeypatch.setenv("WP_URL_MODE", mode)
    manager = object()
    calls = []
    monkeypatch.setattr(dashboard_server, "DockerContainerManager", lambda: manager)

    def serve():
        assert dashboard_server.DashboardRequestHandler.manager is manager
        calls.append("serve")

    server = SimpleNamespace(
        serve_forever=serve, server_close=lambda: calls.append("close")
    )
    monkeypatch.setattr(dashboard_server, "ThreadingHTTPServer", lambda *args: server)
    monkeypatch.setattr(
        dashboard_server, "NginxProxyManager",
        lambda: SimpleNamespace(ensure_proxy=lambda **kwargs: calls.append("proxy")),
    )
    # start_dashboard_server intentionally changes this process-global setting.
    monkeypatch.setenv(dashboard_server.WEB_SERVER_PORT_ENV_VAR, "8080")
    monkeypatch.setattr(dashboard_server.DashboardRequestHandler, "manager", None, raising=False)
    dashboard_server.start_dashboard_server()
    assert calls == (["proxy", "serve", "close"] if mode == "subdomain" else ["serve", "close"])


@pytest.fixture(autouse=True)
def isolated_calls_settings(monkeypatch):
    for key in (
        "WP_MATTERMOST_CALLS_HOST", "WP_MATTERMOST_CALLS_HOST_PORT",
        "WP_MATTERMOST_HOST_PORT", "MM_CALLS_ICE_HOST_OVERRIDE",
        "MM_CALLS_ICE_HOST_PORT_OVERRIDE", "MM_CALLS_UDP_SERVER_ADDRESS",
        "MM_CALLS_TCP_SERVER_ADDRESS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("WP_URL_MODE", "subdomain")


@pytest.mark.parametrize("mode", ["subdomain", "port"])
def test_calls_media_is_published_in_both_url_modes(monkeypatch, mode):
    monkeypatch.setenv("WP_URL_MODE", mode)
    expected = {"8443/tcp": 8443, "8443/udp": 8443}
    if mode == "port":
        expected["8065/tcp"] = 5101

    assert website_published_ports("mattermost") == expected
    assert cli._build_ports("mattermost") == expected
    assert dashboard_server._build_ports("mattermost") == expected


def test_other_proxy_sites_keep_existing_bindings(monkeypatch):
    assert website_published_ports("peppermint") is None
    monkeypatch.setenv("WP_URL_MODE", "port")
    assert website_published_ports("peppermint") == {
        "3000/tcp": 9301, "5003/tcp": 5003,
    }


def test_calls_worker_offset_is_applied_once(monkeypatch):
    monkeypatch.setenv("WP_MATTERMOST_HOST_PORT", "5108")
    monkeypatch.setenv("WP_MATTERMOST_CALLS_HOST_PORT", "8450")

    assert website_published_ports("mattermost") == {
        "8443/tcp": 8450, "8443/udp": 8450,
    }
    environment = website_environment("mattermost", exp_hash="w7")
    assert environment["MM_PLUGINSETTINGS_ENABLE"] == "true"
    assert environment["MM_CALLS_ICE_HOST_OVERRIDE"] == "127.0.0.1"
    assert environment["MM_CALLS_ICE_HOST_PORT_OVERRIDE"] == "8450"
    assert environment["MM_SERVICESETTINGS_SITEURL"] == (
        "http://mattermost--w7.localhost:8080"
    )


def test_calls_remote_overrides_preserve_http_proxy_configuration(monkeypatch):
    monkeypatch.setenv("WP_WEB_SERVER_URL", "https://benchmark.example.test:9443")
    monkeypatch.setenv("WP_MATTERMOST_CALLS_HOST", "192.0.2.20")
    monkeypatch.setenv("WP_MATTERMOST_CALLS_HOST_PORT", "18443")

    environment = website_environment("mattermost", exp_hash="w2")
    assert environment["MM_CALLS_ICE_HOST_OVERRIDE"] == "192.0.2.20"
    assert environment["MM_CALLS_ICE_HOST_PORT_OVERRIDE"] == "18443"
    assert environment["MM_SERVICESETTINGS_SITEURL"] == (
        "https://mattermost--w2.benchmark.example.test:9443"
    )
    assert environment["MM_SERVICESETTINGS_WEBSOCKETURL"] == (
        "wss://mattermost--w2.benchmark.example.test:9443"
    )

    monkeypatch.setenv("MM_CALLS_ICE_HOST_OVERRIDE", "192.0.2.40")
    monkeypatch.setenv("MM_CALLS_ICE_HOST_PORT_OVERRIDE", "28443")
    environment = website_environment("mattermost")
    assert environment["MM_CALLS_ICE_HOST_OVERRIDE"] == "192.0.2.40"
    assert environment["MM_CALLS_ICE_HOST_PORT_OVERRIDE"] == "28443"
    assert website_published_ports("mattermost") == {
        "8443/tcp": 18443, "8443/udp": 18443,
    }


@pytest.mark.parametrize("port", ["0", "65536"])
def test_calls_rejects_invalid_published_port(monkeypatch, port):
    monkeypatch.setenv("WP_MATTERMOST_CALLS_HOST_PORT", port)
    with pytest.raises(ValueError, match="between 1 and 65535"):
        website_published_ports("mattermost")


@pytest.mark.parametrize("mode", ["subdomain", "port"])
def test_recreate_publishes_worker_media_without_removing_conflicts(monkeypatch, mode):
    monkeypatch.setenv("WP_URL_MODE", mode)
    monkeypatch.setenv("WP_MATTERMOST_HOST_PORT", "5108")
    monkeypatch.setenv("WP_MATTERMOST_CALLS_HOST_PORT", "8450")
    monkeypatch.setenv("WP_MATTERMOST_CONTAINER_NAME", "mattermost-w7")
    calls = []
    proxy_calls = []
    manager = SimpleNamespace(reset_container=lambda **kwargs: calls.append(kwargs))
    proxy = SimpleNamespace(ensure_network=lambda: proxy_calls.append("network"))
    monkeypatch.setattr(
        state_reset, "ensure_proxy_serialized",
        lambda proxy: proxy_calls.append("reload"),
    )

    state_reset.recreate_site_container(
        "mattermost", container_manager=manager, proxy_manager=proxy
    )

    call = calls[0]
    assert call["name"] == "mattermost-w7"
    assert call["ports"]["8443/tcp"] == call["ports"]["8443/udp"] == 8450
    assert call["environment"]["MM_CALLS_ICE_HOST_PORT_OVERRIDE"] == "8450"
    assert call["remove_port_conflicts"] is False
    assert ("8065/tcp" in call["ports"]) == (mode == "port")
    assert proxy_calls == (["network", "reload"] if mode == "subdomain" else [])


@pytest.mark.parametrize("http_port,api_port", [(9301, 5003), (19304, 15006)])
def test_peppermint_imported_worker_ports_are_not_offset_twice(http_port, api_port):
    env = dict(os.environ, WP_URL_MODE="port",
               WP_PEPPERMINT_HOST_PORT=str(http_port),
               WP_PEPPERMINT_API_HOST_PORT=str(api_port))
    output = subprocess.check_output(
        [sys.executable, "-c",
         "import json; from webarena_pro_core import website_published_ports; "
         "print(json.dumps(website_published_ports('peppermint')))"],
        env=env, text=True,
    )
    assert json.loads(output) == {"3000/tcp": http_port, "5003/tcp": api_port}


def test_peppermint_runtime_env_keeps_explicit_api_port(monkeypatch):
    monkeypatch.setenv("WP_URL_MODE", "port")
    monkeypatch.setenv("WP_PEPPERMINT_HOST_PORT", "19304")
    monkeypatch.setenv("WP_PEPPERMINT_API_HOST_PORT", "15006")
    assert website_published_ports("peppermint") == {
        "3000/tcp": 19304, "5003/tcp": 15006,
    }


def test_calls_forwards_explicit_native_bind_addresses(monkeypatch):
    # Empty is also a native setting: leave interpretation to the image/plugin.
    monkeypatch.setenv("MM_CALLS_UDP_SERVER_ADDRESS", "")
    monkeypatch.setenv("MM_CALLS_TCP_SERVER_ADDRESS", "192.0.2.30")
    environment = website_environment("mattermost")
    assert environment["MM_CALLS_UDP_SERVER_ADDRESS"] == ""
    assert environment["MM_CALLS_TCP_SERVER_ADDRESS"] == "192.0.2.30"
    monkeypatch.delenv("MM_CALLS_UDP_SERVER_ADDRESS")
    monkeypatch.delenv("MM_CALLS_TCP_SERVER_ADDRESS")
    environment = website_environment("mattermost")
    assert "MM_CALLS_UDP_SERVER_ADDRESS" not in environment
    assert "MM_CALLS_TCP_SERVER_ADDRESS" not in environment
