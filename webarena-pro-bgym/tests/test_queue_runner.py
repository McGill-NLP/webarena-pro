"""Exercise actual coordinator and study scheduling with OS subprocess workers.

The worker's experiments and container operations are fixtures; the queue,
study claim/prewarm flow, environment assignment, and process supervision are
production code. These tests do not require Docker or a model API.
"""

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import textwrap

import pytest

from webarena_pro_bgym import queue_runner
from webarena_pro_bgym.parallel import reserve_worker_slot
from webarena_pro_bgym.task_queue import TaskQueue


WORKER_SCRIPT = """
import argparse
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

from webarena_pro_bgym import prewarm
from webarena_pro_bgym import study as study_module
from webarena_pro_bgym.task_queue import TaskQueue

parser = argparse.ArgumentParser()
parser.add_argument('--study-dir', type=Path, required=True)
parser.add_argument('--task-queue', type=Path, required=True)
parser.add_argument('--queue-worker', required=True)
args = parser.parse_args()
def snapshot():
    return TaskQueue.load(args.task_queue).status()
root = args.task_queue.parent
worker_count = int(os.environ['QUEUE_TEST_WORKERS'])
mode = os.environ.get('QUEUE_TEST_MODE', 'normal')
events_path = args.study_dir / 'events.jsonl'

def event(kind, **values):
    with events_path.open('a') as output:
        output.write(json.dumps({'kind': kind, **values}) + '\\n')

def wait_until(predicate):
    deadline = time.monotonic() + 60
    while not predicate():
        if time.monotonic() >= deadline:
            raise RuntimeError('Fixture synchronization timed out')
        time.sleep(0.01)

def cleanup(*, sites, env):
    event('cleanup', sites=list(sites), slot=prewarm.assigned_runtime_slot(env))

def launch(*, sites, task_id, runtime_slot, env):
    event('prewarm', sites=list(sites), task_id=int(task_id), slot=runtime_slot)
    return SimpleNamespace(wait=lambda: True, cancel=lambda: None)

prewarm.cleanup_runtime_containers = cleanup
prewarm.launch_container_prewarm = launch
study_module.drain_step_verifiers = lambda: None

class Agent:
    def prepare(self):
        pass

    def close(self):
        pass

class Benchmark:
    def prepare_backends(self):
        pass

class Experiment(study_module.WebArenaProExpArgs):
    def __init__(self, row):
        self.task_id = row['task_id']
        self.env_args = SimpleNamespace(
            task_name=f'webarena-pro-bgym.{self.task_id}',
            task_config=SimpleNamespace(task_id=self.task_id, sites=row['sites']),
        )
        self.agent_args = Agent()
        self.err_msg = self.stack_trace = self.worker_fatal_error = None

    def prepare(self, exp_root):
        self.directory = Path(exp_root) / f'webarena-pro-bgym.{self.task_id}'
        self.directory.mkdir(exist_ok=True)
        self.exp_dir = self.directory

    def run(self):
        self._set_logger()
        try:
            self.run_fixture_episode()
        finally:
            self._unset_logger()

    def run_fixture_episode(self):
        claims = [row['task_id'] for row in snapshot()
                  if row['state'] in {'claimed', 'started'} and row['worker_id'] == args.queue_worker]
        event('run', task_id=self.task_id, claims=claims,
              slot=prewarm.assigned_runtime_slot(),
              prewarmed=os.environ.get('WP_PREWARMED_TASK_ID'))
        barrier = root / 'barriers' / args.queue_worker.rsplit('-', 1)[-1]
        barrier.mkdir(parents=True, exist_ok=True)
        (barrier / (args.queue_worker + '.started')).touch()
        wait_until(lambda: len(list(barrier.glob('*.started'))) == worker_count)
        if self.task_id == 0:
            if mode == 'crash':
                os._exit(int(os.environ.get('QUEUE_TEST_EXIT_CODE', '17')))
            if mode == 'hold':
                wait_until(lambda: False)
            if mode == 'task_error':
                self.err_msg = 'Expected fixture task error'
            else:
                # The slow task cannot finish until other workers drain pending
                # work. This proves dynamic pulling without wall-clock thresholds.
                wait_until(lambda: not any(row['state'] == 'pending' for row in snapshot()))
        summary = {'task_id': self.task_id, 'cum_reward': 0 if self.err_msg else 1,
                   'n_steps': 1, 'err_msg': self.err_msg, 'worker_id': args.queue_worker}
        (self.directory / 'summary_info.json').write_text(json.dumps(summary))

class FixtureStudy(study_module.WebArenaProStudy):
    def set_reproducibility_info(self, **kwargs):
        pass

    def save(self):
        # Exercise actual gzip/pickle persistence, including previously run
        # experiments; replacing this with a JSON fixture hid retained RLocks.
        super().save()
        (self.dir / 'study.json').write_text(json.dumps(
            {'task_ids': [exp.task_id for exp in self.exp_args_list]}))

    def get_results(self, **kwargs):
        (self.dir / 'summary_queue.json').write_text(json.dumps(
            {'task_ids': [exp.task_id for exp in self.exp_args_list]}))

study = FixtureStudy.__new__(FixtureStudy)
study.exp_args_list = [Experiment(row) for row in snapshot()]
study.benchmark = Benchmark()
study.dir = args.study_dir
study.run_queue(args.task_queue, args.queue_worker)
"""


@pytest.fixture
def worker_fixture(tmp_path, monkeypatch):
    script = tmp_path / "worker.py"
    script.write_text(textwrap.dedent(WORKER_SCRIPT))
    package = Path(__file__).resolve().parents[1]
    sources = [str(package / "src"), str(package.parent / "webarena-pro-core" / "src")]
    if os.environ.get("PYTHONPATH"):
        sources.append(os.environ["PYTHONPATH"])
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(sources))
    monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "1")
    monkeypatch.setenv("WP_RESET_BACKEND", "container")
    monkeypatch.delenv("WP_ACTIVE_RUNTIME_SLOT", raising=False)
    monkeypatch.delenv("WP_QUEUE_STANDBY_SLOT", raising=False)
    slot_root = tmp_path / "slots"
    slots = []
    cleanups = []

    def reserve(*, sites, worker_index=None):
        slot = reserve_worker_slot(
            sites=sites,
            lock_root=slot_root,
            max_workers=int(os.environ.get("QUEUE_TEST_SLOT_LIMIT", "32")),
            worker_index=worker_index,
        )
        slots.append(slot)
        return slot

    monkeypatch.setattr(queue_runner, "reserve_worker_slot", reserve)
    monkeypatch.setattr(
        queue_runner,
        "cleanup_runtime_containers",
        lambda **kwargs: cleanups.append({
            key: value for key, value in kwargs["env"].items()
            if key in {"WP_PARALLEL_WORKER_INDEX", "WP_ACTIVE_RUNTIME_SLOT", "WP_QUEUE_STANDBY_SLOT"}
        }),
    )
    return {
        "command": [sys.executable, str(script)],
        "slots": slots,
        "slot_root": slot_root,
        "cleanups": cleanups,
    }


def _task_sites(count):
    return {
        task: ["mattermost", "nextcloud"] if task % 3 == 0 else ["mattermost"]
        for task in range(count)
    }


def _assert_released(fixture):
    assert fixture["slots"]
    assert not list(fixture["slot_root"].glob("*/w*"))


@pytest.mark.parametrize("worker_count", [4, 8])
@pytest.mark.parametrize("prewarm", [False, True])
def test_real_workers_pull_uneven_tasks_and_preserve_results(
    tmp_path, monkeypatch, worker_fixture, worker_count, prewarm
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", str(int(prewarm)))
    monkeypatch.setenv("QUEUE_TEST_WORKERS", str(worker_count))
    root = tmp_path / "results"
    task_sites = _task_sites(worker_count * 4)

    assert queue_runner.run_queue_workers(
        task_sites=task_sites, worker_count=worker_count, root_dir=root,
        command=worker_fixture["command"],
    ) == 0

    records = TaskQueue.load(root / "queue.jsonl").status()
    assert all(row["state"] == "done" for row in records)
    worker_dirs = sorted((root / "workers").iterdir())
    assert len(worker_dirs) == worker_count
    assert len(worker_fixture["slots"]) == worker_count * (2 if prewarm else 1)
    counts = []
    observed_tasks = []
    for directory in worker_dirs:
        task_ids = json.loads((directory / "study.json").read_text())["task_ids"]
        result_ids = json.loads((directory / "summary_queue.json").read_text())["task_ids"]
        summaries = [json.loads(path.read_text())
                     for path in directory.glob("*/summary_info.json")]
        assert sorted(task_ids) == sorted(result_ids) == sorted(row["task_id"] for row in summaries)
        assert sorted(task_ids) == sorted(row["task_id"] for row in records
                                        if row["worker_id"] == directory.name)
        assert all(row["cum_reward"] == 1 for row in summaries)
        events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
        runs = [event for event in events if event["kind"] == "run"]
        assert all(1 <= len(event["claims"]) <= (2 if prewarm else 1) for event in runs)
        preparations = [event for event in events if event["kind"] == "prewarm"]
        if prewarm:
            assert len(preparations) <= max(0, len(task_ids) - 1)
            assert len({event["slot"] for event in runs}) == min(2, len(task_ids))
            prepared_ids = {event["task_id"] for event in preparations}
            assert all(event["prewarmed"] == (str(event["task_id"]) if event["task_id"] in prepared_ids else None)
                       for event in runs)
        else:
            assert not preparations
            assert len({event["slot"] for event in runs}) == 1
        assert all(event["sites"] == task_sites[event["task_id"]] for event in preparations)
        counts.append(len(task_ids))
        observed_tasks.extend(task_ids)
        assert (directory / "worker.log").exists()
    assert sorted(observed_tasks) == list(task_sites)
    slow_worker = records[0]["worker_id"]
    assert sum(row["worker_id"] == slow_worker for row in records) == (2 if prewarm else 1)
    assert max(counts) > 4  # A faster worker took tasks beyond a fixed equal split.
    assert not worker_fixture["cleanups"]  # Healthy workers cleaned their own slots.
    _assert_released(worker_fixture)


@pytest.mark.parametrize("prewarm", [False, True])
@pytest.mark.parametrize("exit_code", [0, 17])
def test_crashed_worker_claims_are_interrupted_and_slots_cleaned(
    tmp_path, monkeypatch, worker_fixture, prewarm, exit_code
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", str(int(prewarm)))
    monkeypatch.setenv("QUEUE_TEST_WORKERS", "2")
    monkeypatch.setenv("QUEUE_TEST_MODE", "crash")
    monkeypatch.setenv("QUEUE_TEST_EXIT_CODE", str(exit_code))
    root = tmp_path / "results"

    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(12), worker_count=2, root_dir=root,
        command=worker_fixture["command"],
    ) == 1

    records = TaskQueue.load(root / "queue.jsonl").status()
    interrupted = [row for row in records if row["state"] == "interrupted"]
    assert len(interrupted) == 1
    assert records[0] in interrupted
    assert all(row["state"] == "done" for row in records[1:])
    episodes = [
        event["task_id"]
        for path in root.glob("workers/*/events.jsonl")
        for line in path.read_text().splitlines()
        if (event := json.loads(line))["kind"] == "run"
    ]
    assert sorted(episodes) == list(range(12))
    assert len(worker_fixture["cleanups"]) == (2 if prewarm else 1)
    _assert_released(worker_fixture)


def test_task_failure_makes_coordinator_fail_after_other_tasks_finish(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "0")
    monkeypatch.setenv("QUEUE_TEST_WORKERS", "2")
    monkeypatch.setenv("QUEUE_TEST_MODE", "task_error")
    root = tmp_path / "results"

    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(8), worker_count=2, root_dir=root,
        command=worker_fixture["command"],
    ) == 1

    records = TaskQueue.load(root / "queue.jsonl").status()
    assert records[0]["state"] == "failed"
    assert records[0]["error"] == "Expected fixture task error"
    assert all(row["state"] == "done" for row in records[1:])
    _assert_released(worker_fixture)


def test_partial_startup_failure_stops_started_workers_and_releases_all_slots(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "1")
    monkeypatch.setenv("QUEUE_TEST_WORKERS", "4")
    original_popen = subprocess.Popen
    started = []

    def popen(*args, **kwargs):
        if started:
            raise OSError("Fixture Popen failure")
        process = original_popen(*args, **kwargs)
        started.append(process)
        return process

    monkeypatch.setattr(queue_runner.subprocess, "Popen", popen)
    root = tmp_path / "results"
    previous_handler = signal.getsignal(signal.SIGTERM)
    with pytest.raises(OSError, match="Fixture Popen failure"):
        queue_runner.run_queue_workers(
            task_sites=_task_sites(16), worker_count=4, root_dir=root,
            command=worker_fixture["command"],
        )

    assert started and all(process.poll() is not None for process in started)
    assert signal.getsignal(signal.SIGTERM) is previous_handler
    assert all(row["state"] not in {"claimed", "started"} for row in TaskQueue.load(root / "queue.jsonl").status())
    _assert_released(worker_fixture)


def test_scarce_slots_go_to_active_workers_before_optional_prewarm(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "1")
    monkeypatch.setenv("QUEUE_TEST_WORKERS", "4")
    monkeypatch.setenv("QUEUE_TEST_SLOT_LIMIT", "4")
    root = tmp_path / "results"

    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(16), worker_count=4, root_dir=root,
        command=worker_fixture["command"],
    ) == 0

    assert len(list((root / "workers").iterdir())) == 4
    assert len(worker_fixture["slots"]) == 4
    assert all(row["state"] == "done" for row in TaskQueue.load(root / "queue.jsonl").status())
    _assert_released(worker_fixture)


def test_coordinator_signal_stops_workers_and_interrupts_claims(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "1")
    monkeypatch.setenv("QUEUE_TEST_WORKERS", "2")
    monkeypatch.setenv("QUEUE_TEST_MODE", "hold")
    root = tmp_path / "results"
    original_serve = queue_runner._Coordinator._serve_idle
    original_popen = subprocess.Popen
    started = []
    sent = False

    def popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        started.append(process)
        return process

    def interrupt_when_running(coordinator):
        nonlocal sent
        if not sent and len(list(root.rglob("*.started"))) == 2:
            sent = True
            os.kill(os.getpid(), signal.SIGTERM)
        original_serve(coordinator)

    monkeypatch.setattr(queue_runner.subprocess, "Popen", popen)
    monkeypatch.setattr(queue_runner._Coordinator, "_serve_idle", interrupt_when_running)
    previous_handler = signal.getsignal(signal.SIGTERM)
    with pytest.raises(KeyboardInterrupt, match="Coordinator received signal"):
        queue_runner.run_queue_workers(
            task_sites=_task_sites(16), worker_count=2, root_dir=root,
            command=worker_fixture["command"],
        )

    assert sent
    assert all(process.poll() is not None for process in started)
    assert signal.getsignal(signal.SIGTERM) is previous_handler
    records = TaskQueue.load(root / "queue.jsonl").status()
    assert records[0]["state"] == "interrupted"
    assert all(row["state"] not in {"claimed", "started"} for row in records)
    assert worker_fixture["cleanups"]
    _assert_released(worker_fixture)


RAW_WORKER_PREFIX = """
import argparse, json, os, time
from pathlib import Path
from webarena_pro_bgym.queue_client import QueueClient, MAX_MESSAGE_BYTES
from webarena_pro_bgym.task_queue import TaskQueue
parser = argparse.ArgumentParser()
parser.add_argument('--study-dir', type=Path, required=True)
parser.add_argument('--task-queue', type=Path, required=True)
parser.add_argument('--queue-worker', required=True)
args = parser.parse_args()
root = args.task_queue.parent
client = QueueClient.from_environment()
def wait_until(predicate):
    deadline = time.monotonic() + 30
    while not predicate():
        if time.monotonic() >= deadline:
            raise RuntimeError('Raw worker synchronization timed out')
        time.sleep(0.005)
"""


def _raw_command(body):
    return [sys.executable, "-c", textwrap.dedent(RAW_WORKER_PREFIX) + textwrap.dedent(body)]


@pytest.mark.parametrize("failure", ["invalid", "partial", "oversized", "disconnect", "premature_done"])
def test_malformed_or_disconnected_worker_does_not_lose_unstarted_claim(
    tmp_path, monkeypatch, worker_fixture, failure
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "0")
    monkeypatch.setenv("QUEUE_TEST_PROTOCOL_FAILURE", failure)
    command = _raw_command("""
        task = client.claim()
        failure = os.environ['QUEUE_TEST_PROTOCOL_FAILURE']
        if failure == 'invalid':
            client.writer.write(b'not-json\\n')
        elif failure == 'partial':
            client.writer.write(b'{"action":')
        elif failure == 'oversized':
            client.writer.write(b'x' * (MAX_MESSAGE_BYTES + 1) + b'\\n')
        elif failure == 'premature_done':
            client.writer.write((json.dumps({'action': 'done', 'task_id': task}) + '\\n').encode())
        os._exit(0)
    """)
    root = tmp_path / "results"
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(1), worker_count=1, root_dir=root, command=command,
    ) == 1
    assert TaskQueue.load(root / "queue.jsonl").status()[0]["state"] == "pending"
    assert worker_fixture["cleanups"]
    _assert_released(worker_fixture)


@pytest.mark.parametrize("close_before_exit", [False, True])
def test_final_done_is_drained_and_clean_eof_allows_result_flush(
    tmp_path, monkeypatch, worker_fixture, close_before_exit
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "0")
    monkeypatch.setenv("QUEUE_TEST_CLOSE_BEFORE_EXIT", str(int(close_before_exit)))
    command = _raw_command("""
        task = client.claim()
        client.started(task)
        if os.environ['QUEUE_TEST_CLOSE_BEFORE_EXIT'] == '1':
            client.complete(task)
            client.close()
            time.sleep(0.1)
            (args.study_dir / 'final-result.json').write_text(json.dumps({'task_id': task}))
        else:
            client.writer.write((json.dumps({'action': 'done', 'task_id': task}) + '\\n').encode())
        os._exit(0)
    """)
    root = tmp_path / "results"
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(4), worker_count=4, root_dir=root, command=command,
        max_worker_restarts=0,
    ) == 0
    assert all(row["state"] == "done" for row in TaskQueue.load(root / "queue.jsonl").status())
    if close_before_exit:
        results = [json.loads(path.read_text())["task_id"] for path in root.glob("workers/*/final-result.json")]
        assert sorted(results) == list(range(4))
    assert not worker_fixture["cleanups"]
    _assert_released(worker_fixture)


def test_reaped_worker_is_not_reported_as_disconnect_timeout(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "0")
    command = _raw_command("""
        task = client.claim()
        client.started(task)
        client.complete(task)
        client.close()
        os._exit(0)
    """)
    original_drain = queue_runner._Coordinator._drain
    observed = []

    def drain_after_exit(coordinator, worker):
        original_drain(coordinator, worker)
        if worker.disconnected_at is not None and worker.worker_id not in observed:
            # A loaded coordinator can resume polling after both the grace
            # period and a successful process exit. Reproduce that ordering.
            assert worker.process.wait(timeout=5) == 0
            worker.disconnected_at -= 6
            observed.append(worker.worker_id)

    monkeypatch.setattr(queue_runner._Coordinator, "_drain", drain_after_exit)
    root = tmp_path / "results"
    result = queue_runner.run_queue_workers(
        task_sites=_task_sites(1), worker_count=1, root_dir=root, command=command,
    )
    assert observed
    assert TaskQueue.load(root / "queue.jsonl").status()[0]["state"] == "done"
    assert result == 0
    assert not worker_fixture["cleanups"]
    _assert_released(worker_fixture)


@pytest.mark.parametrize("prewarm", [False, True])
def test_finished_workers_can_take_longer_than_disconnect_grace_to_exit(
    tmp_path, monkeypatch, worker_fixture, prewarm
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", str(int(prewarm)))
    command = _raw_command("""
        completed = []
        task = client.claim()
        while task is not None:
            client.started(task)
            client.complete(task)
            completed.append(task)
            task = client.claim()
        client.close()
        # Model slow interpreter finalizers after normal queue exhaustion.
        time.sleep(6)
        (args.study_dir / 'final-result.json').write_text(json.dumps(completed))
    """)
    root = tmp_path / "results"
    result = queue_runner.run_queue_workers(
        task_sites=_task_sites(4), worker_count=2, root_dir=root, command=command,
    )
    assert all(row["state"] == "done" for row in TaskQueue.load(root / "queue.jsonl").status())
    assert result == 0
    results = [json.loads(path.read_text()) for path in root.glob("workers/*/final-result.json")]
    assert len(results) == 2
    assert sorted(task for tasks in results for task in tasks) == list(range(4))
    assert not worker_fixture["cleanups"]
    _assert_released(worker_fixture)


def test_worker_with_unstarted_claim_can_flush_exception_after_closing_ipc(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "0")
    command = _raw_command("""
        task = client.claim()
        client.close()
        # run_queue closes IPC in finally before Python prints the exception.
        time.sleep(0.2)
        raise RuntimeError('Expected failure while saving the next experiment')
    """)
    root = tmp_path / "results"
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(1), worker_count=1, root_dir=root, command=command,
        max_worker_restarts=0,
    ) == 1
    assert TaskQueue.load(root / "queue.jsonl").status()[0]["state"] == "pending"
    log, = root.glob("workers/*/worker.log")
    assert "RuntimeError: Expected failure while saving the next experiment" in log.read_text()
    assert worker_fixture["cleanups"]
    _assert_released(worker_fixture)


def test_unexpected_disconnect_still_terminates_a_live_worker(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "0")
    command = _raw_command("""
        task = client.claim()
        client.close()
        time.sleep(60)
    """)
    original_drain = queue_runner._Coordinator._drain

    def expire_disconnect(coordinator, worker):
        original_drain(coordinator, worker)
        if worker.disconnected_at is not None:
            worker.disconnected_at -= 6

    monkeypatch.setattr(queue_runner._Coordinator, "_drain", expire_disconnect)
    root = tmp_path / "results"
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(1), worker_count=1, root_dir=root, command=command,
    ) == 1
    assert TaskQueue.load(root / "queue.jsonl").status()[0]["state"] == "pending"
    assert worker_fixture["cleanups"]
    _assert_released(worker_fixture)


def test_lookahead_leaves_tasks_for_startup_and_idle_workers(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "1")
    command = _raw_command("""
        first = client.claim()
        ahead = client.claim(lookahead=True)
        assert ahead is None
        (args.study_dir / 'initial.json').write_text(json.dumps({'task_id': first, 'lookahead': ahead}))
        wait_until(lambda: len(list(root.glob('workers/*/initial.json'))) == 4)
        done = []
        task = first
        while task is not None:
            client.started(task)
            client.complete(task)
            done.append(task)
            task = client.claim()
        (args.study_dir / 'done.json').write_text(json.dumps(done))
        client.close()
    """)
    root = tmp_path / "results"
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(5), worker_count=4, root_dir=root, command=command,
    ) == 0
    initial = [json.loads(path.read_text())["task_id"] for path in root.glob("workers/*/initial.json")]
    done = [task for path in root.glob("workers/*/done.json") for task in json.loads(path.read_text())]
    assert sorted(initial) == [0, 1, 2, 3]
    assert sorted(done) == list(range(5))
    _assert_released(worker_fixture)


def test_idle_worker_receives_unstarted_lookahead_after_other_worker_crashes(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "1")
    command = _raw_command("""
        first = client.claim()
        (args.study_dir / 'claimed').touch()
        wait_until(lambda: len(list(root.glob('workers/*/claimed'))) == 2)
        if first == 0:
            ahead = client.claim(lookahead=True)
            assert ahead is not None
            client.started(first)
            (root / 'reserved.json').write_text(json.dumps(ahead))
            def other_work_done():
                rows = TaskQueue.load(args.task_queue).status()
                return all(row['state'] == 'done' for row in rows if row['task_id'] not in {first, ahead})
            wait_until(other_work_done)
            os._exit(17)
        wait_until(lambda: (root / 'reserved.json').exists())
        completed = []
        task = first
        while task is not None:
            client.started(task)
            client.complete(task)
            completed.append(task)
            task = client.claim()
        (args.study_dir / 'completed.json').write_text(json.dumps(completed))
        client.close()
    """)
    root = tmp_path / "results"
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(6), worker_count=2, root_dir=root, command=command,
        max_worker_restarts=0,
    ) == 1
    rows = TaskQueue.load(root / "queue.jsonl").status()
    assert rows[0]["state"] == "interrupted"
    assert all(row["state"] == "done" for row in rows[1:])
    ahead = json.loads((root / "reserved.json").read_text())
    completed = [task for path in root.glob("workers/*/completed.json") for task in json.loads(path.read_text())]
    assert sorted(completed) == list(range(1, 6))
    assert completed[-1] == ahead
    _assert_released(worker_fixture)


def test_resume_completed_queue_writes_usage_without_launching_workers(tmp_path):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", _task_sites(1))
    task = queue.claim("old")
    queue.started(task, "old")
    queue.complete(task, "old")
    (tmp_path / "queue_run.json").write_text(json.dumps({"prewarm": False}))
    episode = tmp_path / "workers/old/episode"
    episode.mkdir(parents=True)
    (episode / "summary_info.json").write_text("{}")
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(1), worker_count=1, root_dir=tmp_path, command=[], resume=True,
    ) == 0
    run = json.loads((tmp_path / "model_requests.json").read_text())
    assert run["requests"] == []
    assert [g["source_path"] for g in run["coverage_gaps"]] == ["workers/old/episode/summary_info.json"]


def test_resume_repairs_torn_tail_and_runs_only_pending_and_unstarted_tasks(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "1")
    root = tmp_path / "results"
    command = _raw_command("""
        task = client.claim()
        assert client.claim(lookahead=True) is not None
        client.started(task)
        os._exit(17)
    """)
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(7), worker_count=1, root_dir=root, command=command,
        max_worker_restarts=0,
    ) == 1
    original = TaskQueue.load(root / "queue.jsonl").status()
    assert original[0]["state"] == "interrupted"
    assert all(row["state"] == "pending" for row in original[1:])
    assert json.loads((root / "queue_workers.json").read_text())["workers"] == {}
    with (root / "queue.jsonl").open("ab") as journal:
        journal.write(b'{"event":"claimed",')

    monkeypatch.setenv("QUEUE_TEST_WORKERS", "2")
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(7), worker_count=2, root_dir=root,
        command=worker_fixture["command"], resume=True, resume_mode="incomplete",
    ) == 1  # The original interrupted episode stays terminal.
    resumed = TaskQueue.load(root / "queue.jsonl").status()
    assert resumed[0] == original[0]
    assert all(row["state"] == "done" for row in resumed[1:])
    episodes = [json.loads(path.read_text())["task_id"] for path in root.glob("workers/*/*/summary_info.json")]
    assert sorted(episodes) == list(range(1, 7))
    _assert_released(worker_fixture)


def test_resume_refuses_live_previous_worker_without_changing_journal(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "0")
    root = tmp_path / "results"
    queue = TaskQueue.create(root / "queue.jsonl", _task_sites(2))
    queue.claim("old-worker")
    before = queue.path.read_bytes()
    previous = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    try:
        (root / "queue_workers.json").write_text(json.dumps({
            "host": socket.gethostname(), "workers": {"old-worker": previous.pid},
        }))
        with pytest.raises(ValueError, match="still running"):
            queue_runner.run_queue_workers(
                task_sites=_task_sites(2), worker_count=1, root_dir=root,
                command=worker_fixture["command"], resume=True,
            )
        assert queue.path.read_bytes() == before
        assert not worker_fixture["slots"]
    finally:
        os.killpg(previous.pid, signal.SIGKILL)
        previous.wait()


def test_resume_refuses_orphan_prewarm_process_group(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "0")
    root = tmp_path / "results"
    queue = TaskQueue.create(root / "queue.jsonl", _task_sites(2))
    queue.claim("old-worker")
    before = queue.path.read_bytes()
    child_path = tmp_path / "child.pid"
    code = "import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); open(sys.argv[1],'w').write(str(p.pid))"
    leader = subprocess.Popen([sys.executable, "-c", code, str(child_path)], start_new_session=True)
    leader.wait(timeout=10)
    try:
        assert child_path.exists()
        os.killpg(leader.pid, 0)
        (root / "queue_workers.json").write_text(json.dumps({
            "host": socket.gethostname(), "workers": {"old-worker": leader.pid},
        }))
        with pytest.raises(ValueError, match="still running"):
            queue_runner.run_queue_workers(
                task_sites=_task_sites(2), worker_count=1, root_dir=root,
                command=worker_fixture["command"], resume=True,
            )
        assert queue.path.read_bytes() == before
    finally:
        os.killpg(leader.pid, signal.SIGKILL)


def test_journal_failure_still_stops_every_worker_and_closes_pipes(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "0")
    root = tmp_path / "results"
    coordinators = []
    original_init = queue_runner._Coordinator.__init__
    original_record = TaskQueue._record

    def capture_init(coordinator, *args, **kwargs):
        original_init(coordinator, *args, **kwargs)
        coordinators.append(coordinator)

    def fail_after_workers_launch(queue, event):
        if event["event"] in {"started", "abandoned"}:
            raise OSError("Fixture journal write failure")
        return original_record(queue, event)

    monkeypatch.setattr(queue_runner._Coordinator, "__init__", capture_init)
    monkeypatch.setattr(TaskQueue, "_record", fail_after_workers_launch)
    command = _raw_command("""
        task = client.claim()
        (args.study_dir / 'claimed').touch()
        wait_until(lambda: len(list(root.glob('workers/*/claimed'))) == 2)
        client.started(task)
        time.sleep(60)
    """)
    with pytest.raises(OSError, match="journal write failure"):
        queue_runner.run_queue_workers(
            task_sites=_task_sites(4), worker_count=2, root_dir=root, command=command,
        )
    assert len(coordinators) == 1
    workers = coordinators[0].workers
    assert len(workers) == 2
    assert all(worker.process.poll() is not None for worker in workers)
    assert all(worker.request_fd == worker.response_fd == -1 for worker in workers)
    for worker in workers:
        with pytest.raises(ProcessLookupError):
            os.killpg(worker.process.pid, 0)
    _assert_released(worker_fixture)


@pytest.mark.parametrize("prewarm", [False, True])
def test_lone_worker_replaced_after_crash_and_unstarted_claim_recovers_after_cleanup(
    tmp_path, monkeypatch, worker_fixture, prewarm
):
    root = tmp_path / "results"
    cleanup_states = []
    cleanup = queue_runner.cleanup_runtime_containers

    def inspect_cleanup(**kwargs):
        cleanup_states.append([row["state"] for row in TaskQueue.load(root / "queue.jsonl").status()])
        assert kwargs["strict"] is True
        roster = json.loads((root / "queue_workers.json").read_text())
        assert len(roster["workers"]) == 1
        assert all(not queue_runner._pid_is_running(pid) for pid in roster["workers"].values())
        return cleanup(**kwargs)

    monkeypatch.setattr(queue_runner, "cleanup_runtime_containers", inspect_cleanup)
    command = _raw_command("""
        task = client.claim()
        while task is not None:
            roster = json.loads((root / 'queue_workers.json').read_text())
            assert set(roster['workers']) == {args.queue_worker}
            if task == 0 and os.environ['WP_PREWARM_CONTAINERS'] == '1':
                ahead = client.claim(lookahead=True)
                assert ahead == 1
            client.started(task)
            (args.study_dir / f'attempt-{task}').touch()
            if task == 0:
                os._exit(17)
            client.complete(task)
            task = client.claim()
        client.close()
    """)
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(6), worker_count=1, root_dir=root, command=command,
        prewarm=prewarm,
    ) == 1
    rows = TaskQueue.load(root / "queue.jsonl").status()
    assert rows[0]["state"] == "interrupted"
    assert all(row["state"] == "done" for row in rows[1:])
    assert len(list(root.glob("workers/*"))) == 2
    assert rows[0]["worker_id"] != rows[1]["worker_id"]
    assert all(row["worker_id"] == rows[1]["worker_id"] for row in rows[1:])
    assert len(list(root.glob("workers/*/attempt-0"))) == 1
    assert len(cleanup_states) == (2 if prewarm else 1)
    assert all(states[0] == "started" for states in cleanup_states)
    if prewarm:
        assert all(states[1] == "claimed" for states in cleanup_states)
    assert json.loads((root / "queue_workers.json").read_text())["workers"] == {}
    _assert_released(worker_fixture)


def test_distinct_failed_tasks_make_progress_without_exhausting_restart_budget(
    tmp_path, monkeypatch, worker_fixture
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "0")
    root = tmp_path / "results"
    command = _raw_command("""
        task = client.claim()
        while task is not None:
            client.started(task)
            (args.study_dir / f'attempt-{task}').touch()
            if task < 5:
                client.fail(task, 'reproducible timeout')
                os._exit(17)
            client.complete(task)
            task = client.claim()
        client.close()
    """)
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(7), worker_count=1, root_dir=root, command=command,
        max_worker_restarts=1,
    ) == 1
    rows = TaskQueue.load(root / "queue.jsonl").status()
    assert [row["state"] for row in rows] == ["failed"] * 5 + ["done"] * 2
    assert len(list(root.glob("workers/*"))) == 6
    assert len(list(root.glob("workers/*/attempt-*"))) == 7
    assert all(row["retry_count"] == 0 for row in rows)
    _assert_released(worker_fixture)


@pytest.mark.parametrize("claim_first", [False, True])
def test_no_progress_crash_restarts_are_bounded(tmp_path, monkeypatch, worker_fixture, claim_first):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "0")
    monkeypatch.setenv("QUEUE_TEST_CLAIM_FIRST", str(int(claim_first)))
    root = tmp_path / "results"
    command = _raw_command("""
        if os.environ['QUEUE_TEST_CLAIM_FIRST'] == '1':
            client.claim()
        os._exit(17)
    """)
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(3), worker_count=1, root_dir=root, command=command,
        max_worker_restarts=2,
    ) == 1
    assert len(list(root.glob("workers/*"))) == 3
    assert all(row["state"] == "pending" for row in TaskQueue.load(root / "queue.jsonl").status())
    assert len(worker_fixture["cleanups"]) == 3
    assert json.loads((root / "queue_workers.json").read_text())["workers"] == {}
    _assert_released(worker_fixture)


def test_recovered_unstarted_crash_does_not_fail_completed_run(tmp_path, monkeypatch, worker_fixture):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "0")
    root = tmp_path / "results"
    command = _raw_command("""
        task = client.claim()
        marker = root / 'crashed-once'
        if not marker.exists():
            marker.touch()
            os._exit(17)
        while task is not None:
            client.started(task)
            client.complete(task)
            task = client.claim()
        client.close()
    """)
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(3), worker_count=1, root_dir=root, command=command,
    ) == 0
    assert len(list(root.glob("workers/*"))) == 2
    assert all(row["state"] == "done" for row in TaskQueue.load(root / "queue.jsonl").status())
    _assert_released(worker_fixture)


def test_failed_cleanup_keeps_claims_roster_and_slots_unavailable(tmp_path, monkeypatch, worker_fixture):
    root = tmp_path / "results"
    command = _raw_command("""
        task = client.claim()
        assert client.claim(lookahead=True) == 1
        client.started(task)
        os._exit(17)
    """)

    def fail_cleanup(**kwargs):
        raise RuntimeError("fixture container cleanup failed")

    monkeypatch.setattr(queue_runner, "cleanup_runtime_containers", fail_cleanup)
    try:
        with pytest.raises(RuntimeError, match="container cleanup failed"):
            queue_runner.run_queue_workers(
                task_sites=_task_sites(4), worker_count=1, root_dir=root, command=command, prewarm=True,
            )
        assert len(list(root.glob("workers/*"))) == 1
        rows = TaskQueue.load(root / "queue.jsonl").status()
        assert [row["state"] for row in rows] == ["started", "claimed", "pending", "pending"]
        roster = json.loads((root / "queue_workers.json").read_text())
        assert list(roster["workers"]) == [rows[0]["worker_id"]]
        assert roster["runtime_slots"][rows[0]["worker_id"]] == [0, 1]
        assert list(worker_fixture["slot_root"].glob("*/w*"))
    finally:
        for slot in worker_fixture["slots"]:
            slot.release()


@pytest.mark.parametrize("resume_mode", ["continue", "fresh", "incomplete"])
def test_explicit_resume_selects_errors_once_and_preserves_finished_tasks(
    tmp_path, monkeypatch, worker_fixture, resume_mode
):
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "0")
    root = tmp_path / "results"
    queue = TaskQueue.create(root / "queue.jsonl", _task_sites(4))
    for task in range(3):
        assert queue.claim("old") == task
        queue.started(task, "old")
        if task == 0:
            queue.fail(task, "old", "timed out")
        elif task == 1:
            queue.abandon_worker("old", "died")
        else:
            queue.complete(task, "old")
    before = queue.status()
    (root / "queue_run.json").write_text(json.dumps({"prewarm": False}))
    command = _raw_command("""
        task = client.claim()
        while task is not None:
            row = next(row for row in TaskQueue.load(args.task_queue).status() if row['task_id'] == task)
            (args.study_dir / f'resume-{task}.json').write_text(json.dumps(row))
            client.started(task)
            if task == 0:
                client.fail(task, 'still broken')
                os._exit(17)
            client.complete(task)
            task = client.claim()
        client.close()
    """)
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(4), worker_count=1, root_dir=root, command=command,
        resume=True, resume_mode=resume_mode,
    ) == 1
    rows = TaskQueue.load(root / "queue.jsonl").status()
    assert rows[2] == before[2]
    assert rows[3]["state"] == "done"
    if resume_mode == "incomplete":
        assert rows[:2] == before[:2]
        assert not list(root.glob("workers/*/resume-0.json"))
    else:
        assert rows[0]["state"] == "failed"
        assert rows[1]["state"] == "done"
        paths = list(root.glob("workers/*/resume-0.json"))
        assert len(paths) == 1
        row = json.loads(paths[0].read_text())
        assert row["retry_count"] == 1
        assert row["full_retry"] == (resume_mode == "fresh")
        assert row["resume_worker_id"] == (None if resume_mode == "fresh" else "old")
    _assert_released(worker_fixture)


def test_resume_reacquires_and_cleans_orphan_slots_before_abandoning_claims(
    tmp_path, monkeypatch, worker_fixture
):
    root = tmp_path / "results"
    queue = TaskQueue.create(root / "queue.jsonl", _task_sites(3))
    queue.claim("old", max_claims=2)
    queue.started(0, "old")
    queue.claim("old", max_claims=2)
    (root / "queue_run.json").write_text(json.dumps({"prewarm": False}))
    (root / "queue_workers.json").write_text(json.dumps({
        "host": socket.gethostname(), "workers": {"old": 99999999},
        "runtime_slots": {"old": [4, 5]},
    }))
    cleaned = []

    def inspect_cleanup(**kwargs):
        states = [row["state"] for row in TaskQueue.load(queue.path).status()]
        assert states == ["started", "claimed", "pending"]
        cleaned.append(int(kwargs["env"]["WP_ACTIVE_RUNTIME_SLOT"]))
        for slot in (4, 5):
            assert (worker_fixture["slot_root"] / "mattermost" / f"w{slot}").exists()
        assert kwargs["strict"] is True

    monkeypatch.setattr(queue_runner, "cleanup_runtime_containers", inspect_cleanup)
    command = _raw_command("""
        task = client.claim()
        while task is not None:
            client.started(task)
            client.complete(task)
            task = client.claim()
        client.close()
    """)
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(3), worker_count=1, root_dir=root, command=command,
        resume=True, resume_mode="incomplete",
    ) == 1
    assert cleaned == [4, 5]
    assert [row["state"] for row in TaskQueue.load(queue.path).status()] == ["interrupted", "done", "done"]
    _assert_released(worker_fixture)


def test_orphan_recovery_refuses_slots_reused_by_another_run_before_cleanup(
    tmp_path, worker_fixture
):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", _task_sites(2))
    queue.claim("old")
    before = queue.path.read_bytes()
    held = reserve_worker_slot(sites=["mattermost"], worker_index=5, lock_root=worker_fixture["slot_root"])
    try:
        with pytest.raises(RuntimeError, match="Could not reserve"):
            queue_runner._recover_previous_runtimes({
                "workers": {"old": 99999999}, "runtime_slots": {"old": [4, 5]},
            }, queue)
        assert not worker_fixture["cleanups"]
        assert queue.path.read_bytes() == before
        assert (worker_fixture["slot_root"] / "mattermost" / "w5" / "owner.pid").exists()
        assert not (worker_fixture["slot_root"] / "mattermost" / "w4").exists()
    finally:
        held.release()


def test_orphan_recovery_retains_slots_when_cleanup_fails(tmp_path, monkeypatch, worker_fixture):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", _task_sites(2))
    queue.claim("old")
    before = queue.path.read_bytes()

    def fail_cleanup(**kwargs):
        raise RuntimeError("fixture cleanup failure")

    monkeypatch.setattr(queue_runner, "cleanup_runtime_containers", fail_cleanup)
    try:
        with pytest.raises(RuntimeError, match="cleanup failure"):
            queue_runner._recover_previous_runtimes({
                "workers": {"old": 99999999}, "runtime_slots": {"old": [4, 5]},
            }, queue)
        assert queue.path.read_bytes() == before
        assert (worker_fixture["slot_root"] / "mattermost" / "w4").exists()
        assert (worker_fixture["slot_root"] / "mattermost" / "w5").exists()
    finally:
        for slot in worker_fixture["slots"]:
            slot.release()


def test_orphan_recovery_refuses_legacy_roster_without_slot_metadata(tmp_path, worker_fixture):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", _task_sites(2))
    queue.claim("old")
    before = queue.path.read_bytes()
    with pytest.raises(ValueError, match="runtime slot metadata"):
        queue_runner._recover_previous_runtimes({"workers": {"old": 99999999}}, queue)
    assert queue.path.read_bytes() == before
    assert not worker_fixture["cleanups"]
    assert not worker_fixture["slots"]


@pytest.mark.parametrize("limit", [-1, True, 1.5])
def test_restart_budget_validation_happens_before_creating_queue(tmp_path, limit):
    with pytest.raises(ValueError, match="nonnegative integer"):
        queue_runner.run_queue_workers(
            task_sites=_task_sites(1), worker_count=1, root_dir=tmp_path,
            command=[], max_worker_restarts=limit,
        )
    assert not (tmp_path / "queue.jsonl").exists()


@pytest.mark.parametrize("resume_mode", ["continue", "fresh"])
def test_active_and_lookahead_claims_carry_retry_metadata_through_pipes(
    tmp_path, worker_fixture, resume_mode
):
    root = tmp_path / "results"
    queue = TaskQueue.create(root / "queue.jsonl", _task_sites(5))
    for task in (0, 1):
        assert queue.claim("old") == task
        queue.started(task, "old")
        queue.fail(task, "old", "timeout")
    (root / "queue_run.json").write_text(json.dumps({"prewarm": True}))
    command = _raw_command("""
        first = client.claim()
        initial = client.last_claim
        ahead = client.claim(lookahead=True)
        lookahead = client.last_claim
        assert (first, ahead) == (0, 1)
        (args.study_dir / 'claim-metadata.json').write_text(json.dumps([initial, lookahead]))
        for task in (first, ahead):
            client.started(task)
            client.complete(task)
        task = client.claim()
        while task is not None:
            assert client.last_claim['retry_count'] == 0
            assert client.last_claim['full_retry'] is False
            assert client.last_claim['resume_worker_id'] is None
            client.started(task)
            client.complete(task)
            task = client.claim()
        assert client.last_claim is None
        client.close()
    """)
    assert queue_runner.run_queue_workers(
        task_sites=_task_sites(5), worker_count=1, root_dir=root, command=command,
        resume=True, resume_mode=resume_mode,
    ) == 0
    result, = root.glob("workers/*/claim-metadata.json")
    for task_id, row in enumerate(json.loads(result.read_text())):
        assert row == {
            "task_id": task_id, "retry_count": 1, "full_retry": resume_mode == "fresh",
            "resume_worker_id": None if resume_mode == "fresh" else "old",
        }
    _assert_released(worker_fixture)
