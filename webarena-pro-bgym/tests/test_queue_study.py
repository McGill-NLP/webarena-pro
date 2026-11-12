import json
import os
from types import SimpleNamespace

import pytest

from webarena_pro_bgym.parallel import build_worker_environment
from webarena_pro_bgym.study import WebArenaProFatalWorkerError, WebArenaProStudy
from webarena_pro_bgym.task_queue import TaskQueue


def make_worker(monkeypatch, tmp_path, *, prewarm=False, errors=None, prepared=True):
    sites = ["mattermost", "nextcloud"]
    env = build_worker_environment(sites=sites, worker_index=0)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("WP_ACTIVE_RUNTIME_SLOT", "0")
    monkeypatch.setenv("WP_QUEUE_STANDBY_SLOT", "1")
    monkeypatch.setenv("WP_PREWARM_CONTAINERS", "1" if prewarm else "0")
    events = []
    snapshots = []
    errors = errors or {}
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {
        1: ["mattermost"], 2: sites, 3: ["nextcloud"],
    })

    class Client:
        def claim(self, *, lookahead=False):
            return queue.claim("worker", max_claims=2 if lookahead else 1)
        def started(self, task_id):
            queue.started(task_id, "worker")
        def complete(self, task_id):
            queue.complete(task_id, "worker")
        def fail(self, task_id, error):
            queue.fail(task_id, "worker", error)
        def close(self):
            queue.abandon_worker("worker", "Fixture worker exited")

    monkeypatch.setattr("webarena_pro_bgym.queue_client.QueueClient.from_environment", lambda: Client())

    class Experiment:
        def __init__(self, task_id):
            self.env_args = SimpleNamespace(
                task_name=f"webarena-pro-bgym.{task_id}",
                task_config=SimpleNamespace(task_id=task_id, sites=queue.status()[task_id - 1]["sites"]),
            )
            self.agent_args = SimpleNamespace(
                prepare=lambda: None,
                close=lambda: events.append(("close", task_id)),
            )
            self.attempts = 0

        def prepare(self, exp_root):
            assert queue.status()[self.env_args.task_config.task_id - 1]["state"] == "started"
            events.append(("prepare", self.env_args.task_config.task_id))
            self.exp_dir = exp_root / str(self.env_args.task_config.task_id)
            self.exp_dir.mkdir(exist_ok=True)

        def run(self):
            task_id = self.env_args.task_config.task_id
            events.append(("run", task_id, os.environ.get("WP_ACTIVE_RUNTIME_SLOT"),
                           os.environ.get("WP_PREWARMED_TASK_ID")))
            claimed = [r["task_id"] for r in queue.status() if r["state"] in {"claimed", "started"}]
            assert len(claimed) <= (2 if prewarm else 1)
            snapshots.append(claimed)
            failures = errors.get(task_id, [])
            if self.attempts < len(failures):
                self.err_msg = failures[self.attempts]
            self.attempts += 1
            (self.exp_dir / "summary_info.json").write_text(json.dumps({"err_msg": self.err_msg}))

    def launch(**kwargs):
        events.append(("prewarm", kwargs["task_id"], kwargs["sites"], kwargs["runtime_slot"]))
        return SimpleNamespace(wait=lambda: prepared, cancel=lambda: events.append(("cancel",)))

    monkeypatch.setattr("webarena_pro_bgym.prewarm.launch_container_prewarm", launch)
    monkeypatch.setattr("webarena_pro_bgym.prewarm.cleanup_runtime_containers",
                        lambda **kwargs: events.append(("cleanup", tuple(kwargs["sites"]))))
    monkeypatch.setattr("webarena_pro_bgym.study.drain_step_verifiers", lambda: None)
    monkeypatch.setattr(WebArenaProStudy, "set_reproducibility_info", lambda *a, **kw: None)
    monkeypatch.setattr(WebArenaProStudy, "save", lambda self: None)
    monkeypatch.setattr(WebArenaProStudy, "get_results", lambda *a, **kw: None)
    study = WebArenaProStudy.__new__(WebArenaProStudy)
    study.exp_args_list = [Experiment(i) for i in (1, 2, 3)]
    study.benchmark = SimpleNamespace(prepare_backends=lambda: None)
    study.dir = tmp_path
    return study, queue, events, snapshots


def test_queue_runs_only_its_owned_tasks(monkeypatch, tmp_path):
    study, queue, events, _ = make_worker(monkeypatch, tmp_path)
    assert queue.claim("other") == 1
    queue.started(1, "other")
    queue.complete(1, "other")
    WebArenaProStudy.run_queue(study, queue.path, "worker", n_relaunch=2)
    assert [exp.env_args.task_config.task_id for exp in study.exp_args_list] == [2, 3]
    assert all(row["state"] == "done" for row in queue.status())
    assert queue.status()[0]["worker_id"] == "other"


def test_queue_retries_errors_and_keeps_exhausted_failure(monkeypatch, tmp_path):
    study, queue, events, _ = make_worker(monkeypatch, tmp_path, errors={
        1: ["ValueError: transient"], 2: ["ValueError: first", "ValueError: second"],
    })
    WebArenaProStudy.run_queue(study, queue.path, "worker", n_relaunch=2)
    assert [row["state"] for row in queue.status()] == ["done", "failed", "done"]
    assert queue.status()[1]["error"] == "ValueError: second"
    assert [e[1] for e in events if e[0] == "run"] == [1, 1, 2, 2, 3]


@pytest.mark.parametrize("prepared", [True, False])
def test_queue_prewarm_is_bounded_multisite_and_falls_back(monkeypatch, tmp_path, prepared):
    study, queue, events, snapshots = make_worker(monkeypatch, tmp_path, prewarm=True, prepared=prepared)
    WebArenaProStudy.run_queue(study, queue.path, "worker")
    assert snapshots == [[1, 2], [2, 3], [3]]
    assert [event for event in events if event[0] == "prewarm"] == [
        ("prewarm", "2", ("mattermost", "nextcloud"), 1),
        ("prewarm", "3", ("nextcloud",), 0),
    ]
    assert [event for event in events if event[0] == "run"] == [
        ("run", 1, "0", None), ("run", 2, "1", "2" if prepared else None),
        ("run", 3, "0", "3" if prepared else None),
    ]
    assert all(row["state"] == "done" for row in queue.status())


def test_fatal_worker_error_records_failure_and_requeues_lookahead(monkeypatch, tmp_path):
    study, queue, events, _ = make_worker(monkeypatch, tmp_path, prewarm=True,
                                         errors={1: ["RuntimeError: no running event loop"]})
    with pytest.raises(WebArenaProFatalWorkerError):
        WebArenaProStudy.run_queue(study, queue.path, "worker", n_relaunch=3)
    assert [row["state"] for row in queue.status()] == ["failed", "pending", "pending"]
    assert "no running event loop" in queue.status()[0]["error"]
    assert len([event for event in events if event[0] == "run"]) == 1
    assert ("cancel",) in events
    assert ("close", 1) in events


def test_empty_queue_does_not_run_or_divide_by_zero(monkeypatch, tmp_path):
    study, queue, events, _ = make_worker(monkeypatch, tmp_path)
    for task_id in (1, 2, 3):
        assert queue.claim("other") == task_id
        queue.started(task_id, "other")
        queue.complete(task_id, "other")
    WebArenaProStudy.run_queue(study, queue.path, "worker")
    assert study.exp_args_list == []
    assert not [event for event in events if event[0] == "run"]


def test_missing_summary_is_not_acknowledged_as_done(monkeypatch, tmp_path):
    study, queue, _, _ = make_worker(monkeypatch, tmp_path)
    study.exp_args_list[0].run = lambda: None
    WebArenaProStudy.run_queue(study, queue.path, "worker")
    assert queue.status()[0]["state"] == "failed"
    assert "Missing or invalid task summary" in queue.status()[0]["error"]
    assert [row["state"] for row in queue.status()[1:]] == ["done", "done"]


def test_denied_lookahead_keeps_claiming_after_current_task(monkeypatch, tmp_path):
    study, queue, events, _ = make_worker(monkeypatch, tmp_path, prewarm=True)
    from webarena_pro_bgym.queue_client import QueueClient
    client = QueueClient.from_environment()
    original_claim = client.claim
    client.claim = lambda *, lookahead=False: None if lookahead else original_claim()
    monkeypatch.setattr(QueueClient, "from_environment", lambda: client)
    WebArenaProStudy.run_queue(study, queue.path, "worker")
    assert [event[1] for event in events if event[0] == "run"] == [1, 2, 3]
    assert not [event for event in events if event[0] == "prewarm"]
    assert all(row["state"] == "done" for row in queue.status())
