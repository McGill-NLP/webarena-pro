import logging
import os
import tempfile
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from webarena_pro_core import state_reset


class FakeResponse:
    def __init__(self, status=200, body=b""):
        self.status = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.body


class FakeExecContainer:
    def __init__(self, *, exit_code=0, output=b"restored"):
        self.exit_code = exit_code
        self.output = output
        self.exec_calls = []

    def exec_run(self, command, *, workdir=None, user="", environment=None):
        self.exec_calls.append(
            {
                "command": command,
                "workdir": workdir,
                "user": user,
                "environment": environment,
            }
        )
        return self.exit_code, self.output


class FakeDockerContainers:
    def __init__(self, container):
        self.container = container
        self.requested_names = []

    def get(self, name):
        self.requested_names.append(name)
        return self.container


class FakeDockerClient:
    def __init__(self, container):
        self.containers = FakeDockerContainers(container)


class FakeContainerResetManager:
    def __init__(self):
        self.reset_calls = []

    def reset_container(self, **kwargs):
        self.reset_calls.append(kwargs)


def test_reset_api_supports_twenty_registered_sites():
    assert len(state_reset.RESET_API_SITES) == 20


def test_fast_state_restore_sites_remain_explicit_subset():
    assert state_reset.STATE_RESTORE_SITES == {
        "acidwave",
        "erp-next",
        "firefly",
        "flight-search",
        "immich",
        "jobportal",
        "mattermost",
        "metabase",
        "minerva-lite",
        "mydrive",
        "nextcloud",
        "notion",
        "password-manager",
        "penpot",
        "peppermint",
        "pipedrive",
        "thunderbird",
        "travelmap",
        "x-lite",
        "yt-lite",
    }
    assert state_reset.CONTAINER_PREFERRED_RESET_SITES == {
        "acidwave",
        "immich",
        "metabase",
        "penpot",
        "peppermint",
        "thunderbird",
        "x-lite",
    }
    assert state_reset.CONTAINER_RECREATE_RESET_SITES == {
        "acidwave",
        "immich",
        "metabase",
        "penpot",
        "peppermint",
        "thunderbird",
        "x-lite",
    }


def test_site_request_target_uses_explicit_site_url(monkeypatch):
    monkeypatch.setenv("WP_X_LITE_URL", "https://x-lite.example.test/root")

    target = state_reset.site_request_target("x-lite", "/reset")

    assert target.url == "https://x-lite.example.test/root/reset"
    assert target.headers is None


def test_site_request_target_uses_local_proxy_host_header(monkeypatch):
    monkeypatch.delenv("WP_X_LITE_URL", raising=False)
    monkeypatch.delenv("WP_WEB_SERVER_DOMAIN", raising=False)
    monkeypatch.delenv("WP_WEB_SERVER_BIND_HOST", raising=False)
    monkeypatch.delenv("WP_WEB_SERVER_PORT", raising=False)

    target = state_reset.site_request_target("x-lite", "/")

    assert target.url == "http://127.0.0.1:8080/"
    assert target.headers == {"Host": "x-lite--local.localhost:8080"}


def test_restore_site_state_uses_packaged_xlite_get_reset(monkeypatch):
    calls = []
    monkeypatch.setenv("WP_X_LITE_URL", "https://x-lite.example.test")

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(state_reset, "urlopen", fake_urlopen)

    result = state_reset.restore_site_state("x-lite")

    request, timeout = calls[0]
    assert request.get_method() == "GET"
    assert request.full_url == "https://x-lite.example.test/reset"
    assert timeout == state_reset.RESET_REQUEST_TIMEOUT_SECONDS
    assert result.site == "x-lite"
    assert result.method == "GET"


def test_restore_site_state_uses_packaged_minerva_get_reset(monkeypatch):
    calls = []
    monkeypatch.setenv("WP_MINERVA_LITE_URL", "https://minerva.example.test")

    def fake_urlopen(request, timeout):
        calls.append(request)
        return FakeResponse()

    monkeypatch.setattr(state_reset, "urlopen", fake_urlopen)

    result = state_reset.restore_site_state("minerva-lite")

    request = calls[0]
    assert request.get_method() == "GET"
    assert request.full_url == "https://minerva.example.test/reset"
    assert result.site == "minerva-lite"
    assert result.method == "GET"


def test_restore_site_state_uses_packaged_notion_post_reset(monkeypatch):
    calls = []
    monkeypatch.setenv("WP_NOTION_URL", "https://notion.example.test")

    def fake_urlopen(request, timeout):
        calls.append(request)
        return FakeResponse()

    monkeypatch.setattr(state_reset, "urlopen", fake_urlopen)

    result = state_reset.restore_site_state("notion")

    request = calls[0]
    assert request.get_method() == "POST"
    assert request.full_url == "https://notion.example.test/api/reset"
    assert request.data == b""
    assert result.site == "notion"
    assert result.method == "POST"


def test_restore_site_state_uses_packaged_mydrive_post_reset(monkeypatch):
    calls = []
    monkeypatch.setenv("WP_MYDRIVE_URL", "https://mydrive.example.test")

    def fake_urlopen(request, timeout):
        calls.append(request)
        return FakeResponse()

    monkeypatch.setattr(state_reset, "urlopen", fake_urlopen)

    result = state_reset.restore_site_state("mydrive")

    request = calls[0]
    assert request.get_method() == "POST"
    assert request.full_url == "https://mydrive.example.test/api/dev/reset"
    assert request.data == b""
    assert result.site == "mydrive"
    assert result.method == "POST"


@pytest.mark.parametrize(
    "site", ["acidwave", "flight-search", "jobportal", "password-manager"]
)
def test_restore_site_state_uses_packaged_post_reset_endpoint(monkeypatch, site):
    calls = []
    monkeypatch.setenv(
        f"WP_{site.upper().replace('-', '_')}_URL", f"https://{site}.example.test"
    )

    def fake_urlopen(request, timeout):
        calls.append(request)
        return FakeResponse()

    monkeypatch.setattr(state_reset, "urlopen", fake_urlopen)

    result = state_reset.restore_site_state(site)

    request = calls[0]
    assert request.get_method() == "POST"
    assert request.full_url == f"https://{site}.example.test/api/reset"
    assert request.data == b""
    assert result.site == site
    assert result.method == "POST"


@pytest.mark.parametrize(
    "site,env_name",
    [
        ("erp-next", "WP_ERP_NEXT_CONTAINER_NAME"),
        ("firefly", "WP_FIREFLY_CONTAINER_NAME"),
        ("immich", "WP_IMMICH_CONTAINER_NAME"),
        ("mattermost", "WP_MATTERMOST_CONTAINER_NAME"),
        ("metabase", "WP_METABASE_CONTAINER_NAME"),
        ("nextcloud", "WP_NEXTCLOUD_CONTAINER_NAME"),
        ("peppermint", "WP_PEPPERMINT_CONTAINER_NAME"),
        ("thunderbird", "WP_THUNDERBIRD_CONTAINER_NAME"),
    ],
)
def test_restore_site_state_uses_packaged_reset_script(monkeypatch, site, env_name):
    monkeypatch.setenv(env_name, f"{site}-worker-1")
    container = FakeExecContainer()
    client = FakeDockerClient(container)

    result = state_reset.restore_site_state(site, docker_client=client)

    assert client.containers.requested_names == [f"{site}-worker-1"]
    assert container.exec_calls == [
        {
            "command": ("bash", "/usr/local/bin/webarena-reset-state"),
            "workdir": None,
            "user": "",
            "environment": None,
        }
    ]
    assert result.site == site
    assert result.method == "DOCKER_EXEC"
    assert result.url == f"container:{site}-worker-1"
    assert result.status_code == 0


def test_restore_site_state_uses_packaged_penpot_reset_script(monkeypatch):
    monkeypatch.setenv("WP_PENPOT_CONTAINER_NAME", "penpot-worker-1")
    container = FakeExecContainer()
    client = FakeDockerClient(container)

    result = state_reset.restore_site_state("penpot", docker_client=client)

    command = container.exec_calls[0]["command"]
    assert client.containers.requested_names == ["penpot-worker-1"]
    assert command[:2] == ("bash", "-lc")
    assert "/usr/local/bin/webarena-reset-state" in command[2]
    assert container.exec_calls[0]["workdir"] is None
    assert container.exec_calls[0]["environment"] is None
    assert result.method == "DOCKER_EXEC"


def test_restore_site_state_uses_packaged_pipedrive_seed_script(monkeypatch):
    monkeypatch.setenv("WP_PIPEDRIVE_CONTAINER_NAME", "pipedrive-worker-1")
    container = FakeExecContainer()
    client = FakeDockerClient(container)

    result = state_reset.restore_site_state("pipedrive", docker_client=client)

    assert client.containers.requested_names == ["pipedrive-worker-1"]
    assert container.exec_calls == [
        {
            "command": ("node", "scripts/restore-seed-if-empty.js"),
            "workdir": "/app",
            "user": "",
            "environment": {"RESET_TO_SEED_ON_STARTUP": "1"},
        }
    ]
    assert result.site == "pipedrive"
    assert result.method == "DOCKER_EXEC"
    assert result.url == "container:pipedrive-worker-1"
    assert result.status_code == 0


def test_restore_site_state_uses_packaged_yt_lite_sqlite_restore(monkeypatch):
    monkeypatch.setenv("WP_YT_LITE_CONTAINER_NAME", "yt-lite-worker-1")
    container = FakeExecContainer()
    client = FakeDockerClient(container)

    result = state_reset.restore_site_state("yt-lite", docker_client=client)

    command = container.exec_calls[0]["command"]
    assert client.containers.requested_names == ["yt-lite-worker-1"]
    assert command[:2] == ("python", "-c")
    assert "DB_PATH" in command[2]
    assert "keep_thumbnails" in command[2]
    assert "init_db()" in command[2]
    assert container.exec_calls[0]["workdir"] == "/app"
    assert container.exec_calls[0]["environment"] is None
    assert result.method == "DOCKER_EXEC"


def test_restore_site_state_reports_docker_exec_failure(monkeypatch):
    monkeypatch.setenv("WP_PIPEDRIVE_CONTAINER_NAME", "pipedrive-worker-1")
    container = FakeExecContainer(exit_code=2, output=b"restore exploded")
    client = FakeDockerClient(container)

    with pytest.raises(RuntimeError, match="exit code 2: restore exploded"):
        state_reset.restore_site_state("pipedrive", docker_client=client)


def test_recreate_site_container_forces_container_recreate(monkeypatch):
    monkeypatch.setenv("WP_NEXTCLOUD_CONTAINER_NAME", "nextcloud-worker-1")
    monkeypatch.setattr(state_reset, "uses_subdomain_urls", lambda: False)
    monkeypatch.setattr(
        state_reset,
        "ensure_opcache_nojit_file",
        lambda: "/tmp/opcache-nojit.ini",
    )
    manager = FakeContainerResetManager()

    result = state_reset.recreate_site_container("nextcloud", container_manager=manager)

    assert len(manager.reset_calls) == 1
    call = manager.reset_calls[0]
    assert callable(call.pop("post_start"))
    assert call == {
        "name": "nextcloud-worker-1",
        "image": "webarenapro/nextcloud:latest",
        "environment": {
            "WP_NEXTCLOUD_URL": "http://nextcloud--local.localhost:8080",
            "WP_NEXTCLOUD_HOST_PORT": "8080",
            "NEXTCLOUD_TRUSTED_DOMAINS": (
                "localhost * 127.0.0.1 nextcloud--local.localhost "
                "nextcloud--local.localhost:8080"
            ),
        },
        "ports": {"80/tcp": 3101},
        "labels": {
            "webarena-pro-core.managed": "website",
            "webarena-pro-core.site": "nextcloud",
            "webarena-pro-core.exp-hash": "local",
            "webarena-pro-core.upstream-port": "80",
        },
        "network": None,
        "volumes": {
            "/tmp/opcache-nojit.ini": {
                "bind": "/usr/local/etc/php/conf.d/opcache-recommended.ini",
                "mode": "ro",
            }
        },
        "run_options": {},
        "remove_port_conflicts": True,
    }
    assert result.site == "nextcloud"
    assert result.method == "CONTAINER_RECREATE"
    assert result.url == "container:nextcloud-worker-1"


def test_reset_site_rejects_unknown_site():
    with pytest.raises(RuntimeError, match="not supported"):
        state_reset.reset_site("unknown-site")


def test_restore_site_state_sends_site_specific_token(monkeypatch):
    calls = []
    monkeypatch.setenv("WP_TRAVELMAP_URL", "https://travelmap.example.test")
    monkeypatch.setenv("WP_TRAVELMAP_RESET_TOKEN", "site secret")

    def fake_urlopen(request, timeout):
        calls.append(request)
        return FakeResponse()

    monkeypatch.setattr(state_reset, "urlopen", fake_urlopen)

    result = state_reset.restore_site_state("travelmap")

    request = calls[0]
    assert request.get_method() == "POST"
    assert (
        request.full_url == "https://travelmap.example.test/api/reset?token=site+secret"
    )
    assert result.method == "POST"


def test_restore_site_state_tries_next_endpoint_on_not_found(monkeypatch):
    calls = []
    monkeypatch.setenv("WP_TRAVELMAP_URL", "https://travelmap.example.test")

    def fake_urlopen(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 404, "not found", hdrs=None, fp=None)
        return FakeResponse()

    monkeypatch.setattr(state_reset, "urlopen", fake_urlopen)

    result = state_reset.restore_site_state("travelmap")

    assert [request.full_url for request in calls] == [
        "https://travelmap.example.test/api/reset",
        "https://travelmap.example.test/reset",
    ]
    assert result.url == "https://travelmap.example.test/reset"


def test_restore_site_state_rejects_unsupported_site():
    with pytest.raises(RuntimeError, match="does not advertise"):
        state_reset.restore_site_state("unknown-site")


def test_reset_backend_selection_is_owned_by_core(monkeypatch):
    monkeypatch.delenv("WP_RESET_BACKEND", raising=False)

    assert state_reset.reset_backend_for_site("nextcloud") == "state"
    assert state_reset.reset_backend_for_site("penpot") == "container"

    monkeypatch.setenv("WP_RESET_BACKEND", "http")
    assert state_reset.reset_backend_for_site("penpot") == "state"

    monkeypatch.setenv("WP_RESET_BACKEND", "none")
    assert state_reset.reset_backend_for_site("nextcloud") == "none"


def test_core_owns_readiness_and_site_startup_contracts():
    assert state_reset.READINESS_PROBES["acidwave"] == (
        "/api/health",
        '"status":"ok"',
    )
    assert state_reset.READINESS_PROBES["firefly"] == ("/healthcheck", "ok")
    assert state_reset.readiness_timeout_for_site("nextcloud") == 20 * 60
    assert state_reset.reset_snapshot_timeout_for_site("erp-next") == 20 * 60
    penpot = state_reset.site_container_run_overrides("penpot")
    assert penpot["entrypoint"] == "/bin/sh"
    assert penpot["command"][0] == "-ec"
    assert "%(ENV_PENPOT_FLAGS)s" in penpot["command"][1]
    assert "exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf" in penpot["command"][1]


def test_post_start_nextcloud_prepares_snapshot_directory():
    class FakeContainer:
        def __init__(self):
            self.commands = []

        def exec_run(self, command):
            self.commands.append(command)
            return 0, b""

    container = FakeContainer()

    state_reset.post_start_site_setup("nextcloud", container)

    assert container.commands == [
        (
            "sh",
            "-lc",
            "mkdir -p /opt/webarena-seed && chown www-data:www-data /opt/webarena-seed",
        )
    ]


def test_exp_hash_and_host_port_resolve_worker_overrides(monkeypatch):
    monkeypatch.setenv("WP_EXP_HASH", "global")
    monkeypatch.setenv("WP_ERP_NEXT_EXP_HASH", "w3")
    monkeypatch.setenv("WP_ERP_NEXT_HOST_PORT", "19203")

    assert state_reset.exp_hash_for_site("erp-next") == "w3"
    assert state_reset.exp_hash_for_site("x-lite") == "global"
    assert state_reset.host_port_for_site("erp-next") == 19203


def test_restore_site_state_and_wait_orders_snapshot_restore_and_readiness(monkeypatch):
    events = []
    monkeypatch.setattr(
        state_reset,
        "wait_until_reset_snapshot_ready",
        lambda site, **kwargs: events.append(("snapshot", site)),
    )
    monkeypatch.setattr(
        state_reset,
        "restore_site_state",
        lambda site, **kwargs: (
            events.append(("restore", site))
            or state_reset.SiteResetResult(site, "DOCKER_EXEC", f"container:{site}", 0)
        ),
    )
    monkeypatch.setattr(
        state_reset,
        "wait_until_site_ready",
        lambda site, **kwargs: events.append(("ready", site)),
    )

    state_reset.restore_site_state_and_wait("erp-next")

    assert events == [
        ("snapshot", "erp-next"),
        ("restore", "erp-next"),
        ("ready", "erp-next"),
    ]


def test_restore_site_state_and_wait_bootstraps_unavailable_worker(monkeypatch):
    recreated = []
    monkeypatch.setattr(
        state_reset,
        "wait_until_reset_snapshot_ready",
        lambda site, **kwargs: None,
    )

    def fail_restore(site, **kwargs):
        raise RuntimeError("State restore failed: [Errno 61] connection refused")

    monkeypatch.setattr(state_reset, "restore_site_state", fail_restore)
    monkeypatch.setattr(
        state_reset,
        "reset_site_container",
        lambda site, **kwargs: (
            recreated.append(site)
            or state_reset.SiteResetResult(
                site,
                "CONTAINER_RECREATE",
                f"container:{site}",
                0,
            )
        ),
    )

    result = state_reset.restore_site_state_and_wait("x-lite")

    assert recreated == ["x-lite"]
    assert result.method == "CONTAINER_RECREATE"


def test_restore_site_state_and_wait_bootstraps_stopped_worker_container(monkeypatch):
    recreated = []
    monkeypatch.setattr(
        state_reset,
        "wait_until_reset_snapshot_ready",
        lambda site, **kwargs: None,
    )

    def fail_restore(site, **kwargs):
        raise RuntimeError(
            "State restore failed via docker exec in container 'mattermost-w0': "
            '409 Client Error: Conflict ("container abc is not running")'
        )

    monkeypatch.setattr(state_reset, "restore_site_state", fail_restore)
    monkeypatch.setattr(
        state_reset,
        "reset_site_container",
        lambda site, **kwargs: (
            recreated.append(site)
            or state_reset.SiteResetResult(
                site,
                "CONTAINER_RECREATE",
                f"container:{site}",
                0,
            )
        ),
    )

    result = state_reset.restore_site_state_and_wait("mattermost")

    assert recreated == ["mattermost"]
    assert result.method == "CONTAINER_RECREATE"


def test_restore_site_state_and_wait_keeps_application_errors_visible(monkeypatch):
    monkeypatch.setattr(
        state_reset,
        "wait_until_reset_snapshot_ready",
        lambda site, **kwargs: None,
    )

    def fail_restore(site, **kwargs):
        raise RuntimeError("State restore failed: HTTP 500: boom")

    monkeypatch.setattr(state_reset, "restore_site_state", fail_restore)

    with pytest.raises(RuntimeError, match="HTTP 500"):
        state_reset.restore_site_state_and_wait("x-lite")


def test_wait_until_site_ready_checks_body_and_snapshot(monkeypatch):
    calls = []
    monkeypatch.setenv("WP_ACIDWAVE_URL", "https://acidwave.example.test")
    monkeypatch.setattr(
        state_reset,
        "urlopen",
        lambda request, timeout: (
            calls.append((request.full_url, timeout))
            or FakeResponse(body=b'{"status":"ok"}')
        ),
    )
    monkeypatch.setattr(
        state_reset,
        "wait_until_reset_snapshot_ready",
        lambda site: calls.append(("snapshot", site)),
    )

    state_reset.wait_until_site_ready("acidwave", timeout_seconds=1)

    assert calls == [
        ("https://acidwave.example.test/api/health", pytest.approx(1, abs=0.01)),
        ("snapshot", "acidwave"),
    ]


def test_opcache_override_uses_user_scoped_temp_file(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    stale_shared_path = tmp_path / "wp-opcache-nojit.ini"
    stale_shared_path.mkdir()

    path = state_reset.ensure_opcache_nojit_file()

    assert path == str(tmp_path / f"wp-opcache-nojit-{os.getuid()}.ini")
    assert stale_shared_path.is_dir()
    assert (tmp_path / f"wp-opcache-nojit-{os.getuid()}.ini").read_text() == (
        "opcache.jit=0\nopcache.jit_buffer_size=0\n"
    )


def test_penpot_readiness_waits_for_backend_profile(monkeypatch):
    responses = iter([
        b"<html>Penpot frontend</html>",
        b'["^ ","~:id","~u00000000-0000-0000-0000-000000000000"]',
    ])
    urls = []
    monkeypatch.setenv("WP_PENPOT_URL", "https://penpot.example.test")
    monkeypatch.setattr(state_reset.time, "sleep", lambda _seconds: None)

    def probe(request, timeout):
        urls.append(request.full_url)
        return FakeResponse(body=next(responses))

    monkeypatch.setattr(state_reset, "urlopen", probe)
    monkeypatch.setattr(state_reset, "wait_until_reset_snapshot_ready", lambda site: None)
    state_reset.wait_until_site_ready("penpot", timeout_seconds=1)
    assert urls == [
        "https://penpot.example.test/api/rpc/command/get-profile",
        "https://penpot.example.test/api/rpc/command/get-profile",
    ]


def test_flight_search_readiness_requires_backend_health(monkeypatch):
    responses = iter([
        FakeResponse(body=b"<html>Flight Search</html>"),
        FakeResponse(status=503, body=b'{"status":"ok"}'),
        FakeResponse(body=b'{"status":"loading"}'),
        FakeResponse(body=b'{"status":"ok","airports":123}'),
    ])
    urls = []
    monkeypatch.setenv("WP_FLIGHT_SEARCH_URL", "http://flight-search--w3.localhost:8080")
    monkeypatch.setattr(state_reset.time, "sleep", lambda _: None)

    def probe(request, timeout):
        urls.append(request.full_url)
        return next(responses)

    monkeypatch.setattr(state_reset, "urlopen", probe)
    state_reset.wait_until_site_ready("flight-search", timeout_seconds=1)

    assert urls == ["http://flight-search--w3.localhost:8080/api/health"] * 4


def test_readiness_timeout_reports_worker_target_and_respects_remaining_budget(monkeypatch):
    now = [0.0]
    timeouts = []
    sleeps = []
    monkeypatch.setenv("WP_FLIGHT_SEARCH_CONTAINER_NAME", "flight-search-w3")
    monkeypatch.setattr(
        state_reset, "site_request_target",
        lambda site, path: state_reset.SiteRequestTarget(
            "http://127.0.0.1:8080/api/health", {"Host": "flight-search--w3.localhost:8080"}
        ),
    )

    def probe(request, timeout):
        timeouts.append(timeout)
        now[0] += 0.8
        raise TimeoutError("backend unavailable")

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(state_reset, "urlopen", probe)
    monkeypatch.setattr(state_reset, "time", SimpleNamespace(
        monotonic=lambda: now[0], sleep=sleep,
        time=lambda: pytest.fail("wall clock used"),
    ))
    with pytest.raises(RuntimeError) as raised:
        state_reset.wait_until_site_ready("flight-search", timeout_seconds=1)

    assert timeouts == [1]
    assert sleeps == [pytest.approx(0.2)]
    message = str(raised.value)
    for expected in (
        "phase=http_readiness", "container=flight-search-w3",
        "image=webarenapro/flight-search:latest", "GET http://127.0.0.1:8080/api/health",
        "Host='flight-search--w3.localhost:8080'", "backend unavailable",
        "attempts: 1", "elapsed: 1.0s",
    ):
        assert expected in message


def test_snapshot_failure_is_not_retried_or_relabelled_as_http_failure(monkeypatch):
    calls = []
    snapshot_error = RuntimeError("phase=reset_snapshot: missing seed marker")

    def probe(request, timeout):
        calls.append("http")
        return FakeResponse(body=b"office-ready" if "office-health" in request.full_url else b"password")

    def snapshot(site):
        calls.append("snapshot")
        raise snapshot_error

    monkeypatch.setattr(state_reset, "urlopen", probe)
    monkeypatch.setattr(state_reset, "wait_until_reset_snapshot_ready", snapshot)

    with pytest.raises(RuntimeError) as raised:
        state_reset.wait_until_site_ready("nextcloud", timeout_seconds=1)

    assert raised.value is snapshot_error
    assert calls == ["http", "http", "snapshot"]


def test_snapshot_timeout_identifies_phase_and_container(monkeypatch):
    monkeypatch.setenv("WP_NEXTCLOUD_CONTAINER_NAME", "nextcloud-w3")
    client = FakeDockerClient(FakeExecContainer(exit_code=1))

    with pytest.raises(RuntimeError) as raised:
        state_reset.wait_until_reset_snapshot_ready("nextcloud", timeout_seconds=0, docker_client=client)

    assert "phase=reset_snapshot" in str(raised.value)
    assert "container=nextcloud-w3" in str(raised.value)
    assert "/opt/webarena-seed/ready" in str(raised.value)


def test_cold_worker_reports_restore_recreate_and_http_phases(monkeypatch, caplog):
    monkeypatch.setenv("WP_FLIGHT_SEARCH_CONTAINER_NAME", "flight-search-w3")

    def unavailable(*args, **kwargs):
        raise RuntimeError("State restore failed: connection refused")

    monkeypatch.setattr(state_reset, "restore_site_state", unavailable)
    monkeypatch.setattr(
        state_reset, "recreate_site_container",
        lambda site, **kwargs: state_reset.SiteResetResult(
            site, "CONTAINER_RECREATE", "container:flight-search-w3", 0
        ),
    )
    monkeypatch.setattr(
        state_reset, "urlopen",
        lambda request, timeout: FakeResponse(body=b'{"status":"ok","airports":123}'),
    )

    with caplog.at_level(logging.INFO, logger=state_reset.__name__):
        result = state_reset.restore_site_state_and_wait("flight-search")

    assert result.method == "CONTAINER_RECREATE"
    assert "phase=state_restore container=flight-search-w3 failed after" in caplog.text
    assert "phase=container_recreate container=flight-search-w3 completed after" in caplog.text
    assert "phase=http_readiness ready after" in caplog.text


def test_nextcloud_readiness_requires_office_after_login(monkeypatch):
    replies = iter([
        FakeResponse(body=b"password"),
        FakeResponse(status=503, body=b"Office startup pending"),
        FakeResponse(body=b"password"),
        FakeResponse(body=b"office-ready"),
    ])
    calls = []
    monkeypatch.setenv("WP_NEXTCLOUD_URL", "http://nextcloud--worker.localhost:8080")
    monkeypatch.setattr(state_reset.time, "sleep", lambda _: None)
    def probe(request, timeout):
        calls.append(request.full_url)
        return next(replies)
    monkeypatch.setattr(state_reset, "urlopen", probe)
    monkeypatch.setattr(state_reset, "wait_until_reset_snapshot_ready", lambda site: None)
    state_reset.wait_until_site_ready("nextcloud", timeout_seconds=1)
    assert calls == [
        "http://nextcloud--worker.localhost:8080/login",
        "http://nextcloud--worker.localhost:8080/webarena-office-health.php",
    ] * 2


def test_nextcloud_external_office_configuration_is_explicit(monkeypatch):
    from webarena_pro_core import website_environment
    monkeypatch.setenv("WP_COLLABORA_URL", "https://office.example.test")
    monkeypatch.setenv("WP_COLLABORA_INTERNAL_URL", "http://office-service:9980")
    monkeypatch.setenv("WP_NEXTCLOUD_CALLBACK_URL", "http://nextcloud-service")
    env = website_environment("nextcloud", exp_hash="worker")
    assert env["WP_COLLABORA_URL"] == "https://office.example.test"
    assert env["WP_COLLABORA_INTERNAL_URL"] == "http://office-service:9980"
    assert env["WP_NEXTCLOUD_CALLBACK_URL"] == "http://nextcloud-service"


def test_nextcloud_missing_office_endpoint_fails_before_task_start(monkeypatch):
    from urllib.error import HTTPError
    calls = []
    def probe(request, timeout):
        calls.append(request.full_url)
        if "office-health" in request.full_url:
            raise HTTPError(request.full_url, 404, "Not Found", {}, None)
        return FakeResponse(body=b"password")
    monkeypatch.setattr(state_reset, "urlopen", probe)
    with pytest.raises(state_reset.NextcloudOfficeImageError, match="Rebuild/deploy"):
        state_reset.wait_until_site_ready("nextcloud", timeout_seconds=1)
    assert len(calls) == 2


def test_nextcloud_reports_definitive_office_startup_failure(monkeypatch):
    from io import BytesIO
    from urllib.error import HTTPError
    def probe(request, timeout):
        if "office-health" in request.full_url:
            raise HTTPError(request.full_url, 503, "Unavailable", {}, BytesIO(
                b"Office startup failed; inspect /tmp/webarena-office-startup.log"
            ))
        return FakeResponse(body=b"password")
    monkeypatch.setattr(state_reset, "urlopen", probe)
    with pytest.raises(state_reset.NextcloudOfficeImageError, match="office-startup.log"):
        state_reset.wait_until_site_ready("nextcloud", timeout_seconds=1)
