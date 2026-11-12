import json
from pathlib import Path

import pytest

from webarena_pro_harbor.cli import build_runtime, main, select_tasks


def test_task_selection_keeps_split_and_site_boundaries():
    selected = select_tasks("test", "all", "1,002")
    assert {task.task_id for task in selected} == {"001", "002"}
    with pytest.raises(ValueError, match="Tasks not found"):
        select_tasks("dev", "all", "001")
    with pytest.raises(ValueError, match="Tasks not found"):
        select_tasks("test", "all", "999999")
    task = selected[0]
    assert select_tasks("test", task.website, task.task_id)[0].task_id == task.task_id


@pytest.mark.parametrize("command", ["serve", "finalize"])
def test_existing_runtime_commands_delegate_to_mcp(tmp_path, monkeypatch, command):
    calls = []

    async def invoke(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(f"webarena_pro_mcp.server.{command}", invoke)
    socket = tmp_path / "control.sock"
    flags = ["webarena-pro-harbor", command, "--socket", str(socket)]
    if command == "serve":
        config, evidence = tmp_path / "session.json", tmp_path / "evidence"
        flags += ["--config", str(config), "--directory", str(evidence), "--port", "8080"]
    monkeypatch.setattr("sys.argv", flags)
    main()
    if command == "serve":
        assert calls == [((config, evidence, socket, 8080), {"host": "0.0.0.0"})]
    else:
        assert calls == [((socket, 360), {})]


def test_build_runtime_bundles_core_browser_helpers_and_media(tmp_path, monkeypatch):
    packages = {
        "webarena-pro-core",
        "webarena-pro-media",
        "webarena-pro-mcp",
        "webarena-pro-harbor",
    }
    for name in packages:
        package = tmp_path / name
        package.mkdir()
        (package / "pyproject.toml").touch()
    built = set()

    def run(command, *, check):
        assert check
        if command[:2] == ["uv", "build"]:
            name = Path(command[-1]).name
            built.add(name)
            (Path(command[command.index("--out-dir") + 1]) / f"{name}.whl").touch()
        else:
            assert command[:-1] == [
                "docker",
                "build",
                "--tag",
                "webarena-pro-harbor:test",
                "--platform",
                "linux/amd64",
            ]
            context = Path(command[-1])
            assert {p.stem for p in (context / "wheels").glob("*.whl")} == packages
            assert "COPY wheels/" in (context / "Dockerfile").read_text()

    monkeypatch.setattr("webarena_pro_harbor.cli.subprocess.run", run)
    build_runtime(tmp_path, "webarena-pro-harbor:test", "linux/amd64")
    assert built == packages


@pytest.mark.parametrize(
    ("flags", "profile", "enabled"),
    [
        ([], "standard", True),
        (["--browser-only"], "standard", False),
        (["--native-audio", "--native-video"], "omni", True),
        (["--native-audio"], "omni", True),
        (["--native-video"], "omni", True),
    ],
)
def test_export_cli_selects_media_profile(tmp_path, monkeypatch, task, flags, profile, enabled):
    output = tmp_path / "export"
    monkeypatch.setattr(
        "sys.argv", ["webarena-pro-harbor", "export", "--output", str(output), *flags]
    )
    monkeypatch.setattr("webarena_pro_harbor.cli.select_tasks", lambda *_: [task])
    main()
    config = json.loads(
        (output / "webarena-pro-dev-fixture/environment/browser/episode.json").read_text()
    )
    assert config["media"]["profile"] == profile
    assert config["media"]["enabled"] is enabled
    assert config["media"]["audio"] == ("--native-audio" in flags)
    assert config["media"]["video"] == ("--native-video" in flags)


def test_export_cli_enables_private_screenshot_recording(tmp_path, monkeypatch, task):
    output = tmp_path / "screenshots"
    monkeypatch.setattr("sys.argv", ["webarena-pro-harbor", "export", "--output", str(output),
                                    "--browser-only", "--record-screenshots"])
    monkeypatch.setattr("webarena_pro_harbor.cli.select_tasks", lambda *_: [task])
    main()
    config = json.loads((output / "webarena-pro-dev-fixture/environment/browser/episode.json").read_text())
    assert config["record_screenshots"] is True
    assert config["media"]["enabled"] is False
    assert config["max_steps"] == 50


@pytest.mark.parametrize(
    "flags",
    [
        ["--browser-only", "--native-audio"],
        ["--browser-only", "--native-video"],
        ["--browser-only", "--native-audio", "--native-video"],
    ],
)
def test_export_cli_rejects_incompatible_media(tmp_path, monkeypatch, capsys, flags):
    output = tmp_path / "export"
    monkeypatch.setattr(
        "sys.argv", ["webarena-pro-harbor", "export", "--output", str(output), *flags]
    )
    monkeypatch.setattr("webarena_pro_harbor.cli.select_tasks", lambda *_: [])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "Error:" in capsys.readouterr().err
    assert not output.exists()
