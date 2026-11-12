import multiprocessing
import os
import time

import pytest

from webarena_pro_core.runtime_locks import docker_lifecycle_slot, docker_timeout, runtime_lock


def _hold_slot(ready, release):
    with docker_lifecycle_slot():
        ready.set()
        release.wait(10)


def _compete(start, counts, guard):
    start.wait(10)
    with docker_lifecycle_slot():
        with guard:
            counts[0] += 1
            counts[1] = max(counts[1], counts[0])
        time.sleep(0.04)
        with guard:
            counts[0] -= 1
            counts[2] += 1


@pytest.fixture(autouse=True)
def isolated_locks(monkeypatch, tmp_path):
    monkeypatch.setenv("WP_RUNTIME_LOCK_DIR", str(tmp_path))
    monkeypatch.setenv("WP_DOCKER_LIFECYCLE_SLOTS", "4")
    monkeypatch.setenv("WP_DOCKER_LOCK_TIMEOUT_SECONDS", "10")


def test_sixteen_processes_share_four_slots():
    context = multiprocessing.get_context("spawn")
    start, guard = context.Event(), context.Lock()
    counts = context.Array("i", [0, 0, 0])
    workers = [context.Process(target=_compete, args=(start, counts, guard)) for _ in range(16)]
    try:
        for worker in workers:
            worker.start()
        start.set()
        for worker in workers:
            worker.join(15)
            assert worker.exitcode == 0
        assert list(counts)[::2] == [0, 16]
        assert 1 < counts[1] <= 4
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
            worker.join(5)


def test_worker_death_releases_permit_and_wait_is_bounded(monkeypatch):
    monkeypatch.setenv("WP_DOCKER_LIFECYCLE_SLOTS", "1")
    context = multiprocessing.get_context("spawn")
    ready, release = context.Event(), context.Event()
    worker = context.Process(target=_hold_slot, args=(ready, release))
    worker.start()
    try:
        assert ready.wait(10)
        monkeypatch.setenv("WP_DOCKER_LOCK_TIMEOUT_SECONDS", "0.05")
        with pytest.raises(TimeoutError, match="docker-lifecycle.*1 slot"):
            with docker_lifecycle_slot():
                pytest.fail("the worker still owns the only permit")
        worker.terminate()
        worker.join(5)
        with docker_lifecycle_slot():
            pass
    finally:
        if worker.is_alive():
            worker.terminate()
        worker.join(5)


def test_nested_calls_and_exceptions_release_permits(monkeypatch):
    monkeypatch.setenv("WP_DOCKER_LIFECYCLE_SLOTS", "1")
    with pytest.raises(ValueError, match="operation failed"):
        with runtime_lock("container:example"), docker_lifecycle_slot():
            with runtime_lock("container:example"), docker_lifecycle_slot():
                raise ValueError("operation failed")
    with docker_lifecycle_slot():
        pass


@pytest.mark.skipif(os.name == "nt", reason="fork is Unix-only")
def test_forked_child_does_not_inherit_parent_permit(monkeypatch):
    monkeypatch.setenv("WP_DOCKER_LIFECYCLE_SLOTS", "1")
    context = multiprocessing.get_context("fork")
    ready, release = context.Event(), context.Event()
    worker = context.Process(target=_hold_slot, args=(ready, release))
    try:
        with docker_lifecycle_slot():
            worker.start()
            assert not ready.wait(0.15)
        assert ready.wait(5)
        release.set()
        worker.join(5)
        assert worker.exitcode == 0
    finally:
        if worker.is_alive():
            worker.terminate()
        worker.join(5)


@pytest.mark.parametrize("value", ["0", "-2", "nan", "inf", "invalid"])
def test_invalid_timeout_fails_with_setting_name(monkeypatch, value):
    monkeypatch.setenv("WP_DOCKER_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="WP_DOCKER_TIMEOUT_SECONDS"):
        docker_timeout()


def test_fractional_slot_count_fails(monkeypatch):
    monkeypatch.setenv("WP_DOCKER_LIFECYCLE_SLOTS", "1.5")
    with pytest.raises(ValueError, match="WP_DOCKER_LIFECYCLE_SLOTS"):
        with docker_lifecycle_slot():
            pass
