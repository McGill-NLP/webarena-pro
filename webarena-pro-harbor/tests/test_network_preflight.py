import subprocess

import pytest

from webarena_pro_harbor.cli import main
from webarena_pro_harbor.network_preflight import preflight_networks


class DockerPool:
    def __init__(self, capacity, *, fail_cleanup=False):
        self.capacity = capacity
        self.created = []
        self.active = set()
        self.removed = []
        self.fail_cleanup = fail_cleanup

    def run(self, command, *, check, capture_output, text, timeout):
        assert check and capture_output and text and 0 < timeout <= 30
        if command[:3] == ["docker", "network", "create"]:
            if len(self.active) >= self.capacity:
                raise subprocess.CalledProcessError(
                    1, command, stderr="could not find an available, non-overlapping IPv4 address pool"
                )
            network_id = f"{len(self.created) + 1:064x}"
            self.created.append(command)
            self.active.add(network_id)
            return subprocess.CompletedProcess(command, 0, network_id + "\n", "")
        assert command[:3] == ["docker", "network", "rm"]
        assert len(command) == 4
        network_id = command[3]
        assert network_id in self.active  # Never delete someone else's network.
        self.removed.append(network_id)
        if self.fail_cleanup:
            raise subprocess.CalledProcessError(1, command, stderr="network has active endpoints")
        self.active.remove(network_id)
        return subprocess.CompletedProcess(command, 0, network_id + "\n", "")


def test_capacity_probe_holds_both_networks_for_every_concurrent_trial(monkeypatch):
    pool = DockerPool(12)
    monkeypatch.setattr("webarena_pro_harbor.network_preflight.subprocess.run", pool.run)
    assert preflight_networks(6) == {"concurrency": 6, "networks": 12, "reserved": False}
    assert len(pool.created) == len(pool.removed) == 12
    assert not pool.active
    assert len({command[-1] for command in pool.created}) == 12
    assert len({command[command.index("--label") + 1] for command in pool.created}) == 1
    assert ["--internal" in command for command in pool.created] == [False, True] * 6


@pytest.mark.parametrize("capacity", [0, 1, 11])
def test_exhaustion_fails_before_trials_and_releases_partial_allocation(monkeypatch, capacity):
    pool = DockerPool(capacity)
    monkeypatch.setattr("webarena_pro_harbor.network_preflight.subprocess.run", pool.run)
    with pytest.raises(RuntimeError, match=f"{capacity}/12 networks allocated") as exc:
        preflight_networks(6)
    assert "non-overlapping IPv4 address pool" in str(exc.value)
    assert "reduce concurrency" in str(exc.value)
    assert not pool.active
    assert len(pool.removed) == capacity


def test_cleanup_failure_reports_exact_ids_and_fails_preflight(monkeypatch):
    pool = DockerPool(2, fail_cleanup=True)
    monkeypatch.setattr("webarena_pro_harbor.network_preflight.subprocess.run", pool.run)
    with pytest.raises(RuntimeError, match="Could not remove these probe network IDs") as exc:
        preflight_networks()
    assert len(pool.removed) == 2
    assert all(network_id in str(exc.value) for network_id in pool.active)


def test_creation_timeout_releases_known_ids_and_reports_uncertain_probe(monkeypatch):
    pool = DockerPool(2)

    def run(command, **kwargs):
        if command[:3] == ["docker", "network", "create"] and pool.created:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return pool.run(command, **kwargs)

    monkeypatch.setattr("webarena_pro_harbor.network_preflight.subprocess.run", run)
    with pytest.raises(RuntimeError, match="Inspect possible unfinished probe wp-preflight-"):
        preflight_networks()
    assert not pool.active and len(pool.removed) == 1


def test_interrupt_still_releases_allocated_networks(monkeypatch):
    pool = DockerPool(2)

    def run(command, **kwargs):
        if command[:3] == ["docker", "network", "create"] and pool.created:
            raise KeyboardInterrupt
        return pool.run(command, **kwargs)

    monkeypatch.setattr("webarena_pro_harbor.network_preflight.subprocess.run", run)
    with pytest.raises(KeyboardInterrupt) as exc:
        preflight_networks()
    assert not pool.active and len(pool.removed) == 1
    assert "Inspect possible unfinished probe wp-preflight-" in exc.value.__notes__[0]


def test_invalid_docker_id_is_not_used_for_cleanup(monkeypatch):
    pool = DockerPool(2)

    def run(command, **kwargs):
        if command[:3] == ["docker", "network", "create"] and pool.created:
            return subprocess.CompletedProcess(command, 0, "untrusted-id\n", "")
        return pool.run(command, **kwargs)

    monkeypatch.setattr("webarena_pro_harbor.network_preflight.subprocess.run", run)
    with pytest.raises(RuntimeError, match="Docker returned no valid network ID") as exc:
        preflight_networks()
    assert "Inspect possible unfinished probe" in str(exc.value)
    assert not pool.active and len(pool.removed) == 1


def test_missing_docker_is_an_actionable_preflight_failure(monkeypatch):
    def run(*args, **kwargs):
        raise FileNotFoundError("docker executable not found")

    monkeypatch.setattr("webarena_pro_harbor.network_preflight.subprocess.run", run)
    with pytest.raises(RuntimeError, match="Verify the Docker context/daemon") as exc:
        preflight_networks()
    assert "docker executable not found" in str(exc.value)


@pytest.mark.parametrize("concurrency,timeout", [
    (0, 120), (-1, 120), (1.5, 120), (True, 120), (1025, 120),
    (1, 0), (1, float("nan")), (1, float("inf")),
])
def test_invalid_parameters_do_not_touch_docker(monkeypatch, concurrency, timeout):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid arguments must not reach Docker")

    monkeypatch.setattr("webarena_pro_harbor.network_preflight.subprocess.run", unexpected)
    with pytest.raises(ValueError):
        preflight_networks(concurrency, timeout)


def test_cli_failure_is_nonzero_for_shell_launch_guard(monkeypatch, capsys):
    pool = DockerPool(1)
    monkeypatch.setattr("webarena_pro_harbor.network_preflight.subprocess.run", pool.run)
    monkeypatch.setattr("sys.argv", ["webarena-pro-harbor", "preflight-networks", "--concurrency", "6"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "Do not start the study" in capsys.readouterr().err
    assert not pool.active


def test_cli_success_reports_no_reservation(monkeypatch, capsys):
    pool = DockerPool(2)
    monkeypatch.setattr("webarena_pro_harbor.network_preflight.subprocess.run", pool.run)
    monkeypatch.setattr("sys.argv", ["webarena-pro-harbor", "preflight-networks"])
    main()
    assert "not reserved" in capsys.readouterr().out
