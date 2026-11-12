import argparse
import os
from dataclasses import dataclass

import pytest
from docker.errors import APIError

from webarena_pro_core import cli
from webarena_pro_core.docker import ImagePullResult


@dataclass
class FakeContainerInfo:
    name: str
    status: str = "running"
    health: str = "unknown"


class FakeContainerManager:
    def __init__(self):
        self.started = []
        self.stopped = []
        self.builds = []
        self.architecture = "arm64"

    def ensure_container_running(self, **kwargs):
        self.started.append(kwargs)
        return FakeContainerInfo(name=kwargs["name"])

    def get_container_url(self, *, name, preferred_container_ports):
        return f"http://localhost/{name}"

    def image_architecture(self, image):
        return self.architecture

    def build_image(self, *, path, tag, log=None):
        self.builds.append((path, tag))
        self.architecture = "arm64"
        return self.architecture

    def stop_container(self, name):
        self.stopped.append(name)


class FakePullManager:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.pulls = []

    def pull_image(self, image, *, log=None):
        self.pulls.append(image)
        outcome = self.outcomes[image]
        if isinstance(outcome, Exception):
            raise outcome
        return ImagePullResult(status=outcome, platform=None)


@pytest.mark.parametrize(
    ("status", "message"),
    [("pulled", "Pulled:"), ("updated", "Updated:"), ("already-current", "Already current:")],
)
def test_env_pull_reports_registry_result(monkeypatch, capsys, status, message):
    manager = FakePullManager({"registry/nextcloud:latest": status})
    monkeypatch.setattr(cli, "DockerContainerManager", lambda: manager)
    monkeypatch.setattr(cli, "_resolve_image", lambda name: "registry/nextcloud:latest")
    monkeypatch.setenv("NO_COLOR", "1")

    assert cli.main(["env", "pull", "nextcloud"]) == 0

    assert manager.pulls == ["registry/nextcloud:latest"]
    assert f"{message} registry/nextcloud:latest" in capsys.readouterr().out


def test_env_pull_failure_returns_nonzero_without_success_message(monkeypatch, capsys):
    manager = FakePullManager({"registry/nextcloud:latest": APIError("registry unavailable")})
    monkeypatch.setattr(cli, "DockerContainerManager", lambda: manager)
    monkeypatch.setattr(cli, "_resolve_image", lambda name: "registry/nextcloud:latest")

    assert cli.main(["env", "pull", "nextcloud"]) == 1

    output = capsys.readouterr().out
    assert "Failed to pull" in output
    assert "registry unavailable" in output
    assert not any(message in output for message in ["Pulled:", "Updated:", "Already current:"])


@pytest.mark.parametrize("fails", [False, True])
def test_env_pull_all_checks_every_image_and_returns_failure_if_any(monkeypatch, capsys, fails):
    manager = FakePullManager({
        "registry/nextcloud:latest": APIError("registry unavailable") if fails else "updated",
        "registry/minerva-lite:latest": "already-current",
        "registry/x-lite:latest": "pulled",
    })
    monkeypatch.setattr(cli, "DockerContainerManager", lambda: manager)
    monkeypatch.setattr(cli, "_iter_known_envs", lambda: [
        ("nextcloud", "registry/nextcloud:latest"),
        ("minerva-lite", "registry/minerva-lite:latest"),
        ("x-lite", "registry/x-lite:latest"),
    ])
    monkeypatch.setenv("NO_COLOR", "1")

    assert cli.main(["env", "pull", "all"]) == int(fails)

    assert manager.pulls == list(manager.outcomes)
    output = capsys.readouterr().out
    assert "Already current: registry/minerva-lite:latest" in output
    assert "Pulled: registry/x-lite:latest" in output
    if fails:
        assert "Failed to pull registry/nextcloud:latest" in output
        assert "Updated: registry/nextcloud:latest" not in output
    else:
        assert "Updated: registry/nextcloud:latest" in output


def test_env_pull_all_with_no_known_images(monkeypatch, capsys):
    manager = FakePullManager({})
    monkeypatch.setattr(cli, "DockerContainerManager", lambda: manager)
    monkeypatch.setattr(cli, "_iter_known_envs", lambda: [])

    assert cli.main(["env", "pull", "all"]) == 0

    assert manager.pulls == []
    assert "Nothing to pull." in capsys.readouterr().out


def test_paint_respects_force_color_and_no_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("WEBARENA_PRO_NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")

    assert cli._paint("ready", cli._Ansi.GREEN) == "\033[32mready\033[0m"

    monkeypatch.setenv("NO_COLOR", "1")

    assert cli._paint("ready", cli._Ansi.GREEN) == "ready"


def test_help_output_is_colored_when_forced(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("WEBARENA_PRO_NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")

    help_text = cli.build_parser().format_help()

    assert "\033[" in help_text
    assert "usage:" in help_text


def test_help_command_is_top_level_only(capsys):
    parser = cli.build_parser()

    args = parser.parse_args(["help"])

    assert cli.cmd_help(args) == 0
    assert "usage: webarena-pro" in capsys.readouterr().out

    with pytest.raises(SystemExit) as error:
        parser.parse_args(["help", "env"])
    assert error.value.code == 2


def test_env_help_subcommand_is_not_registered():
    parser = cli.build_parser()

    with pytest.raises(SystemExit) as error:
        parser.parse_args(["env", "help"])
    assert error.value.code == 2


def test_main_forwards_run_args_before_argparse_handles_options(monkeypatch):
    calls = []

    monkeypatch.setattr(
        cli,
        "cmd_run",
        lambda args: calls.append(args.args) or 0,
    )

    assert cli.main(
        ["run", "--split", "test", "--n-jobs", "6", "--agent-model", "gemini/gemini-3.5-flash"]
    ) == 0
    assert calls == [
        ["--split", "test", "--n-jobs", "6", "--agent-model", "gemini/gemini-3.5-flash"]
    ]


def test_find_local_bgym_src_checks_working_directory(monkeypatch, tmp_path):
    source_root = tmp_path / "webarena-pro-bgym" / "src"
    package_root = source_root / "webarena_pro_bgym"
    package_root.mkdir(parents=True)
    (package_root / "run_cli.py").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert cli._find_local_webarena_pro_bgym_src() == source_root


def test_cmd_run_prefers_sibling_bgym_checkout(monkeypatch, tmp_path):
    source_root = tmp_path / "webarena-pro-bgym" / "src"
    calls = []

    class Completed:
        returncode = 7

    def fake_run(command, *, env, check):
        calls.append({"command": command, "env": env, "check": check})
        return Completed()

    monkeypatch.setattr(cli, "_find_local_webarena_pro_bgym_src", lambda: source_root)
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert cli.cmd_run(argparse.Namespace(args=["-h"])) == 7
    assert calls[0]["command"] == [
        cli.sys.executable,
        "-m",
        "webarena_pro_bgym.run_cli",
        "-h",
    ]
    assert calls[0]["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(source_root)
    assert calls[0]["check"] is False


def test_env_dashboard_alias_starts_website_viewer(monkeypatch):
    from webarena_pro_core import dashboard_server

    calls = []

    monkeypatch.setattr(
        dashboard_server,
        "start_dashboard_server",
        lambda **kwargs: calls.append(kwargs),
    )

    parser = cli.build_parser()
    args = parser.parse_args(["env", "dashboard", "--host", "0.0.0.0", "--port", "8090"])

    assert args.func(args) == 0
    assert calls == [{"host": "0.0.0.0", "port": 8090}]


def test_serve_remains_website_viewer_alias():
    parser = cli.build_parser()
    args = parser.parse_args(["serve"])

    assert args.func is cli.cmd_serve
    assert args.host == "127.0.0.1"
    assert args.port == 8080


def test_start_parser_accepts_login_flags():
    parser = cli.build_parser()

    single = parser.parse_args(["env", "start", "x-lite", "--login"])
    multiple = parser.parse_args(["env", "start", "x-lite", "minerva-lite"])
    all_sites = parser.parse_args(["env", "start", "all", "--auto_login"])
    dashed = parser.parse_args(["env", "start", "all", "--auto-login"])
    stop_multiple = parser.parse_args(["env", "stop", "x-lite", "minerva-lite"])

    assert single.name == ["x-lite"]
    assert single.login is True
    assert single.auto_login is False
    assert single.wait_timeout == cli.DEFAULT_START_WAIT_SECONDS
    assert multiple.name == ["x-lite", "minerva-lite"]
    assert stop_multiple.name == ["x-lite", "minerva-lite"]
    assert all_sites.login is False
    assert all_sites.auto_login is True
    assert all_sites.name == ["all"]
    assert dashed.auto_login is True


def test_iter_target_envs_accepts_multiple_names():
    targets = cli._iter_target_envs(["x-lite", "minerva-lite", "x-lite"])

    assert [name for name, _ in targets] == ["x-lite", "minerva-lite"]


def test_iter_target_envs_rejects_all_with_explicit_names():
    with pytest.raises(SystemExit, match="either 'all' or explicit environment names"):
        cli._iter_target_envs(["all", "x-lite"])


def test_mattermost_readiness_uses_system_ping_endpoint():
    assert (
        cli._readiness_url("mattermost", "http://mattermost.localhost")
        == "http://mattermost.localhost/api/v4/system/ping"
    )
    assert cli._readiness_response_ok("mattermost", 200, b'{"status":"OK"}') is True
    assert cli._readiness_response_ok("mattermost", 200, b'{"status":"starting"}') is False
    assert cli._readiness_response_ok("mattermost", 200, b"<html>Mattermost</html>") is False


def test_immich_readiness_uses_backend_ping_endpoint():
    assert (
        cli._readiness_url("immich", "http://immich.localhost")
        == "http://immich.localhost/api/server/ping"
    )
    assert cli._readiness_response_ok("immich", 200, b'{"res":"pong"}') is True
    assert cli._readiness_response_ok("immich", 200, b'{"res":"starting"}') is False
    assert cli._readiness_response_ok("immich", 200, b"<html>Immich</html>") is False


def test_generic_readiness_keeps_root_probe_semantics():
    assert cli._readiness_url("x-lite", "http://x-lite.localhost") == "http://x-lite.localhost"
    assert cli._readiness_response_ok("x-lite", 204, b"") is True
    assert cli._readiness_response_ok("x-lite", 503, b"") is False


def test_cmd_start_with_login_writes_storage_state_for_started_site(monkeypatch, tmp_path):
    manager = FakeContainerManager()
    login_calls = []
    wait_calls = []

    monkeypatch.setattr(cli, "DockerContainerManager", lambda: manager)
    monkeypatch.setattr(cli, "uses_subdomain_urls", lambda: False)
    monkeypatch.setattr(cli, "_iter_target_envs", lambda name: [("x-lite", "image")])
    monkeypatch.setattr(cli, "_build_ports", lambda name: {"7860/tcp": 7101})
    monkeypatch.setattr(cli, "_network_name", lambda: None)
    monkeypatch.setattr(cli, "container_name_for_site", lambda name: name)
    monkeypatch.setattr(cli, "website_environment", lambda name, exp_hash=None: None)
    monkeypatch.setattr(cli, "labels_for_site", lambda name, exp_hash=None: {})
    monkeypatch.setattr(cli, "active_exp_hash", lambda: "local")
    monkeypatch.setattr(cli, "_preferred_ports", lambda name: ["7860"])
    monkeypatch.setattr(
        cli,
        "_auto_login_started_sites",
        lambda site_urls, **kwargs: login_calls.append((site_urls, kwargs)),
    )
    monkeypatch.setattr(
        cli,
        "_wait_until_http_ready",
        lambda site, url, **kwargs: wait_calls.append((site, url, kwargs)),
    )

    args = argparse.Namespace(
        name=["x-lite"],
        login=True,
        auto_login=False,
        auth_dir=str(tmp_path),
        login_browser="chromium",
        headed=False,
        login_max_attempts=2,
        wait_timeout=33,
    )

    assert cli.cmd_start(args) == 0

    assert manager.started[0]["name"] == "x-lite"
    assert manager.started[0]["run_options"] == {"init": True}
    assert wait_calls == [
        (
            "x-lite",
            "http://localhost/x-lite",
            {"timeout_seconds": 33.0},
        )
    ]
    assert login_calls == [
        (
            {"x-lite": "http://localhost/x-lite"},
            {
                "auth_dir": tmp_path,
                "browser_name": "chromium",
                "headless": True,
                "max_attempts": 2,
            },
        )
    ]


def test_cmd_start_reloads_proxy_before_waiting_in_subdomain_mode(monkeypatch):
    manager = FakeContainerManager()
    events = []

    class FakeProxy:
        def ensure_network(self):
            events.append("network")

        def ensure_proxy(self, log=None):
            events.append("proxy")

    monkeypatch.setattr(cli, "DockerContainerManager", lambda: manager)
    monkeypatch.setattr(cli, "NginxProxyManager", FakeProxy)
    monkeypatch.setattr(cli, "uses_subdomain_urls", lambda: True)
    monkeypatch.setattr(cli, "_iter_target_envs", lambda name: [("mattermost", "image")])
    monkeypatch.setattr(cli, "_build_ports", lambda name: None)
    monkeypatch.setattr(cli, "_network_name", lambda: "webarena-net")
    monkeypatch.setattr(cli, "_public_url", lambda name: f"http://{name}.localhost")
    monkeypatch.setattr(cli, "container_name_for_site", lambda name: name)
    monkeypatch.setattr(cli, "website_environment", lambda name, exp_hash=None: None)
    monkeypatch.setattr(cli, "labels_for_site", lambda name, exp_hash=None: {})
    monkeypatch.setattr(cli, "active_exp_hash", lambda: "local")
    monkeypatch.setattr(
        cli,
        "_wait_until_http_ready",
        lambda site, url, **kwargs: events.append(("wait", site, url)),
    )

    args = argparse.Namespace(
        name=["mattermost"],
        login=False,
        auto_login=False,
        auth_dir=".auth",
        login_browser="chromium",
        headed=False,
        login_max_attempts=3,
        wait_timeout=cli.DEFAULT_START_WAIT_SECONDS,
    )

    assert cli.cmd_start(args) == 0

    assert events == [
        "network",
        "proxy",
        ("wait", "mattermost", "http://mattermost.localhost"),
    ]


def test_auto_login_flag_is_only_for_start_all():
    args = argparse.Namespace(name=["x-lite"], auto_login=True)

    with pytest.raises(SystemExit, match="--auto_login"):
        cli.cmd_start(args)


def test_cmd_stop_accepts_multiple_site_names(monkeypatch):
    manager = FakeContainerManager()

    monkeypatch.setattr(cli, "DockerContainerManager", lambda: manager)
    monkeypatch.setattr(cli, "uses_subdomain_urls", lambda: False)
    monkeypatch.setattr(
        cli,
        "_iter_target_envs",
        lambda names: [("x-lite", "image"), ("minerva-lite", "image")],
    )
    monkeypatch.setattr(cli, "container_name_for_site", lambda name: f"{name}-container")

    args = argparse.Namespace(name=["x-lite", "minerva-lite"])

    assert cli.cmd_stop(args) == 0

    assert manager.stopped == ["x-lite-container", "minerva-lite-container"]


def test_cmd_stop_single_site_reloads_proxy(monkeypatch):
    manager = FakeContainerManager()
    events = []

    class FakeProxy:
        def ensure_proxy(self, log=None):
            events.append("reload-proxy")

        def stop_proxy(self, log=None):
            events.append("stop-proxy")
            return True

    def stop_container(name):
        events.append(f"stop:{name}")
        manager.stopped.append(name)

    manager.stop_container = stop_container

    monkeypatch.setattr(cli, "DockerContainerManager", lambda: manager)
    monkeypatch.setattr(cli, "NginxProxyManager", FakeProxy)
    monkeypatch.setattr(cli, "uses_subdomain_urls", lambda: True)
    monkeypatch.setattr(cli, "_iter_target_envs", lambda names: [("x-lite", "image")])
    monkeypatch.setattr(cli, "container_name_for_site", lambda name: f"{name}-container")

    args = argparse.Namespace(name=["x-lite"])

    assert cli.cmd_stop(args) == 0

    assert events == ["stop:x-lite-container", "reload-proxy"]


def test_cmd_stop_all_stops_proxy_after_site_containers(monkeypatch):
    manager = FakeContainerManager()
    events = []

    class FakeProxy:
        def ensure_proxy(self, log=None):
            events.append("reload-proxy")

        def stop_proxy(self, log=None):
            events.append("stop-proxy")
            return True

    def stop_container(name):
        events.append(f"stop:{name}")
        manager.stopped.append(name)

    manager.stop_container = stop_container

    monkeypatch.setattr(cli, "DockerContainerManager", lambda: manager)
    monkeypatch.setattr(cli, "NginxProxyManager", FakeProxy)
    monkeypatch.setattr(cli, "uses_subdomain_urls", lambda: True)
    monkeypatch.setattr(
        cli,
        "_iter_target_envs",
        lambda names: [("x-lite", "image"), ("minerva-lite", "image")],
    )
    monkeypatch.setattr(cli, "container_name_for_site", lambda name: f"{name}-container")

    args = argparse.Namespace(name=["all"])

    assert cli.cmd_stop(args) == 0

    assert events == [
        "stop:x-lite-container",
        "stop:minerva-lite-container",
        "stop-proxy",
    ]


def test_cmd_start_builds_native_thunderbird_on_arm(monkeypatch, tmp_path):
    manager = FakeContainerManager()
    manager.architecture = "amd64"
    context = tmp_path / "thunderbird"
    context.mkdir()

    monkeypatch.setattr(cli, "DockerContainerManager", lambda: manager)
    monkeypatch.setattr(cli, "uses_subdomain_urls", lambda: False)
    monkeypatch.setattr(cli, "_iter_target_envs", lambda name: [("thunderbird", "image")])
    monkeypatch.setattr(cli, "_build_ports", lambda name: {"80/tcp": 5201})
    monkeypatch.setattr(cli, "_network_name", lambda: None)
    monkeypatch.setattr(cli, "container_name_for_site", lambda name: name)
    monkeypatch.setattr(cli, "website_environment", lambda name, exp_hash=None: None)
    monkeypatch.setattr(cli, "labels_for_site", lambda name, exp_hash=None: {})
    monkeypatch.setattr(cli, "active_exp_hash", lambda: "local")
    monkeypatch.setattr(cli, "_preferred_ports", lambda name: ["80"])
    monkeypatch.setattr(cli, "configured_docker_platform", lambda: None)
    monkeypatch.setattr(cli.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(cli, "_find_local_website_context", lambda name: context)
    monkeypatch.setattr(cli, "_wait_until_http_ready", lambda site, url, **kwargs: None)

    args = argparse.Namespace(
        name=["thunderbird"],
        login=False,
        auto_login=False,
        auth_dir=".auth",
        login_browser="chromium",
        headed=False,
        login_max_attempts=3,
        wait_timeout=cli.DEFAULT_START_WAIT_SECONDS,
    )

    assert cli.cmd_start(args) == 0

    assert manager.builds == [(str(context), "image")]
    assert manager.started[0]["name"] == "thunderbird"


def test_penpot_readiness_requires_backend_profile():
    assert cli._readiness_url("penpot", "http://localhost") == "http://localhost/api/rpc/command/get-profile"
    assert cli._readiness_response_ok("penpot", 200, b'["^ ","~:id","0000"]')
    assert not cli._readiness_response_ok("penpot", 200, b"<html>Penpot</html>")
    assert not cli._readiness_response_ok("penpot", 503, b'["~:id"]')


def test_erpnext_readiness_requires_backend_ping():
    assert cli._readiness_url("erp-next", "http://localhost") == "http://localhost/api/method/ping"
    assert cli._readiness_response_ok("erp-next", 200, b'{"message":"pong"}')
    assert not cli._readiness_response_ok("erp-next", 200, b"<html>Setup</html>")
