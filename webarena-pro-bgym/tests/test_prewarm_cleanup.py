"""Strict cleanup is a prerequisite for safely replacing crashed workers."""

from types import SimpleNamespace
import subprocess

import pytest

from webarena_pro_bgym import prewarm


@pytest.mark.parametrize("failure", ["exit", "timeout", "spawn"])
def test_strict_cleanup_reports_failures_and_legacy_cleanup_remains_best_effort(monkeypatch, failure):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 120)
        if failure == "spawn":
            raise OSError("cannot spawn cleanup")
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(prewarm.subprocess, "run", run)
    with pytest.raises((RuntimeError, subprocess.TimeoutExpired, OSError)):
        prewarm.cleanup_runtime_containers(sites=["mattermost"], env={}, strict=True)
    assert "--strict" in commands[0]
    prewarm.cleanup_runtime_containers(sites=["mattermost"], env={})
    assert "--strict" not in commands[1]


def test_strict_stop_propagates_container_removal_failure(monkeypatch):
    def fail_stop(site):
        raise RuntimeError("Docker removal failed")

    monkeypatch.setattr("webarena_pro_core.state_reset.stop_site_container", fail_stop)
    with pytest.raises(RuntimeError, match="Docker removal"):
        prewarm.main(["stop", "--site", "mattermost", "--strict"])
    assert prewarm.main(["stop", "--site", "mattermost"]) == 0
