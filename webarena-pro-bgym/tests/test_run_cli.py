import sys

import pytest

import webarena_pro_bgym.run_cli as run_cli


@pytest.mark.parametrize("split", ["dev", "test"])
def test_run_cli_uses_tiered_and_preserves_split(split, monkeypatch):
    calls = []
    monkeypatch.setattr(run_cli, "run_tiered_main", lambda argv: calls.append(argv) or 0)
    args = ["--split", split, "--site", "nextcloud", "--list"]
    assert run_cli.main(args) == 0
    assert calls == [args]


def test_run_cli_uses_sys_argv(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["webarena-pro run", "--split", "test"])
    monkeypatch.setattr(run_cli, "run_tiered_main", lambda argv: calls.append(argv) or 0)
    assert run_cli.main() == 0
    assert calls == [["--split", "test"]]


def test_run_cli_dispatches_dashboard(monkeypatch):
    calls = []
    monkeypatch.setattr(run_cli, "run_dashboard_main", lambda argv: calls.append(argv) or 0)
    assert run_cli.main(["dashboard", "--study-dir", "/tmp/study"]) == 0
    assert calls == [["--study-dir", "/tmp/study"]]


@pytest.mark.parametrize("mode", ["eval", "tiered"])
@pytest.mark.parametrize("args", [[], ["--all"], ["--help"]])
def test_run_cli_rejects_removed_modes(mode, args, capsys):
    with pytest.raises(SystemExit) as error:
        run_cli.main([mode, *args])
    assert error.value.code == 2
    output = capsys.readouterr().err
    assert f"{mode} subcommand was removed" in output
    assert "use webarena-pro run [options]" in output


@pytest.mark.parametrize("args", [[], ["-h"], ["--help"]])
def test_run_cli_help(args, capsys):
    assert run_cli.main(args) == 0
    output = capsys.readouterr().out
    assert "tiered" in output
    assert "--split dev" in output
    assert "--split {dev,test}" in output
    assert "--max-steps" in output
    assert "--no-autostart" in output
    assert "run dashboard" in output
    assert "run eval" not in output
    assert "run tiered" not in output


def test_run_cli_rejects_help_subcommand(capsys):
    with pytest.raises(SystemExit) as error:
        run_cli.main(["help", "dashboard"])
    assert error.value.code == 2
    assert "the 'help' subcommand was removed" in capsys.readouterr().err
