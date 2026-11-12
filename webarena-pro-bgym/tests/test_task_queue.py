import json

import pytest

from webarena_pro_bgym import task_queue as task_queue_module
from webarena_pro_bgym.task_queue import TaskQueue


def test_fifo_lifecycle_preserves_order_and_multisite_metadata(tmp_path):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {9: ["a", "b", "a"], 2: ["b"], 7: []})

    for task_id in (9, 2, 7):
        assert queue.claim("worker") == task_id
        queue.started(task_id, "worker")
        queue.complete(task_id, "worker")

    assert queue.claim("worker") is None
    records = queue.status()
    assert [row["task_id"] for row in records] == [9, 2, 7]
    assert records[0]["sites"] == ["a", "b"]
    assert all(row["state"] == "done" for row in records)
    assert all(row["claimed_at"] <= row["started_at"] <= row["finished_at"] for row in records)
    assert TaskQueue.load(queue.path).status() == records
    initial = json.loads(queue.path.read_text().splitlines()[0])
    assert [task["position"] for task in initial["tasks"]] == [0, 1, 2]


def test_started_work_and_lookahead_both_count_toward_claim_limit(tmp_path):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {i: ["a"] for i in range(5)})

    assert queue.claim("one") == 0
    queue.started(0, "one")
    assert queue.claim("one") is None
    assert queue.claim("two", max_claims=2) == 1
    queue.started(1, "two")
    assert queue.claim("two", max_claims=2) == 2
    assert queue.claim("two", max_claims=2) is None
    queue.complete(1, "two")
    assert queue.claim("two", max_claims=2) == 3
    queue.complete(0, "one")
    assert queue.claim("one") == 4


def test_unstarted_claims_requeue_in_original_fifo_order(tmp_path):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {9: ["a"], 2: ["b"], 7: ["c"]})
    assert queue.claim("lost", max_claims=2) == 9
    assert queue.claim("lost", max_claims=2) == 2
    queue.started(9, "lost")

    assert queue.abandon_worker("lost", "worker exited") == 2
    assert queue.abandon_worker("lost", "worker exited") == 0
    rows = queue.status()
    assert [row["state"] for row in rows] == ["interrupted", "pending", "pending"]
    assert rows[0]["worker_id"] == "lost"
    assert rows[0]["error"] == "worker exited"
    assert rows[0]["started_at"] is not None
    assert rows[0]["finished_at"] is not None
    assert rows[1]["worker_id"] is None
    assert rows[1]["claimed_at"] is None
    assert rows[1]["started_at"] is None
    assert rows[1]["finished_at"] is None
    assert queue.claim("survivor") == 2
    queue.started(2, "survivor")
    queue.complete(2, "survivor")
    assert queue.claim("survivor") == 7
    assert TaskQueue.load(queue.path).status() == queue.status()


def test_abandoned_claim_returns_ahead_of_later_pending_tasks(tmp_path):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {9: ["a"], 2: ["b"], 7: ["c"]})
    assert queue.claim("first") == 9
    assert queue.claim("second") == 2
    assert queue.abandon_worker("first", "never started") == 1
    assert queue.claim("third") == 9
    assert queue.abandon_worker("second", "never started") == 1
    assert queue.claim("fourth") == 2
    assert queue.claim("fifth") == 7


def test_complete_and_fail_require_owned_started_task(tmp_path):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {1: ["a"]})
    with pytest.raises(ValueError, match="not claimed"):
        queue.started(1, "owner")
    queue.claim("owner")
    before = queue.path.read_bytes()

    with pytest.raises(ValueError, match="not claimed"):
        queue.started(1, "someone-else")
    with pytest.raises(ValueError, match="not started"):
        queue.complete(1, "owner")
    with pytest.raises(ValueError, match="not started"):
        queue.fail(1, "owner", "not running")
    assert queue.path.read_bytes() == before

    queue.started(1, "owner")
    with pytest.raises(ValueError, match="not claimed"):
        queue.started(1, "owner")
    with pytest.raises(ValueError, match="not started"):
        queue.complete(1, "someone-else")
    with pytest.raises(ValueError, match="not started"):
        queue.fail(1, "someone-else", "wrong owner")
    queue.complete(1, "owner")
    before = queue.path.read_bytes()
    with pytest.raises(ValueError, match="not started"):
        queue.fail(1, "owner", "too late")
    with pytest.raises(ValueError, match="Unknown task"):
        queue.complete(999, "owner")
    assert queue.abandon_worker("owner", "already done") == 0
    assert queue.path.read_bytes() == before
    assert queue.status()[0]["state"] == "done"


def test_failures_and_terminal_tasks_stay_terminal_after_abandonment(tmp_path):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {i: ["a"] for i in range(3)})
    assert queue.claim("worker") == 0
    queue.started(0, "worker")
    queue.fail(0, "worker", "browser failed")
    assert queue.claim("worker") == 1
    queue.started(1, "worker")
    queue.complete(1, "worker")
    assert queue.claim("worker") == 2
    queue.started(2, "worker")
    assert queue.abandon_worker("worker", "worker exited") == 1
    assert queue.claim("replacement") is None

    rows = TaskQueue.load(queue.path).status()
    assert [row["state"] for row in rows] == ["failed", "done", "interrupted"]
    assert rows[0]["error"] == "browser failed"
    assert rows[2]["error"] == "worker exited"


def test_replay_does_not_implicitly_change_outstanding_claims(tmp_path):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {i: ["a"] for i in range(4)})
    queue.claim("worker", max_claims=2)
    queue.started(0, "worker")
    queue.claim("worker", max_claims=2)
    original_bytes = queue.path.read_bytes()

    resumed = TaskQueue.load(queue.path, repair=True)
    assert resumed.status() == queue.status()
    assert resumed.path.read_bytes() == original_bytes
    # The caller performs process cleanup before explicitly abandoning claims.
    assert resumed.abandon_worker("worker", "old processes stopped") == 2
    assert resumed.claim("new-worker") == 1
    resumed.started(1, "new-worker")
    resumed.complete(1, "new-worker")
    assert TaskQueue.load(queue.path).status() == resumed.status()


@pytest.mark.parametrize("tail", [b'{"event":"started",', b'{"event":"started"}', b'\xff'])
def test_partial_final_line_is_ignored_until_explicit_repair(tmp_path, tail):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {1: ["a"], 2: ["b"]})
    queue.claim("worker")
    complete_bytes = queue.path.read_bytes()
    with queue.path.open("ab") as output:
        output.write(tail)

    inspected = TaskQueue.load(queue.path)
    assert inspected.status() == queue.status()
    assert queue.path.read_bytes() == complete_bytes + tail
    with pytest.raises(RuntimeError, match="repair=True"):
        inspected.started(1, "worker")
    assert queue.path.read_bytes() == complete_bytes + tail

    resumed = TaskQueue.load(queue.path, repair=True)
    assert resumed.status() == queue.status()
    assert queue.path.read_bytes() == complete_bytes
    resumed.started(1, "worker")
    resumed.complete(1, "worker")
    assert TaskQueue.load(queue.path).status() == resumed.status()
    assert queue.path.read_bytes().startswith(complete_bytes)


@pytest.mark.parametrize("bad_line", [
    b'{"event":broken}\n',
    b'\xff\n',
    b'\n',
    b'{"event":"unknown"}\n',
    b'{"event":"done","task_id":1,"worker_id":"worker","at":1}\n',
])
def test_malformed_complete_line_refuses_replay_and_repair(tmp_path, bad_line):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {1: ["a"]})
    queue.claim("worker")
    complete_bytes = queue.path.read_bytes()
    damaged = complete_bytes + bad_line + b'{"incomplete":'
    queue.path.write_bytes(damaged)

    for repair in (False, True):
        with pytest.raises(ValueError, match="line 3"):
            TaskQueue.load(queue.path, repair=repair)
        assert queue.path.read_bytes() == damaged


def test_replay_rejects_wrong_owner_and_incorrect_abandonment_set(tmp_path):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {1: ["a"], 2: ["b"]})
    queue.claim("owner")
    initial = queue.path.read_bytes()
    events = [
        {"event": "started", "task_id": 1, "worker_id": "wrong-owner", "at": 1},
        {"event": "abandoned", "task_ids": [1, 2], "worker_id": "owner", "error": "exit", "at": 1},
        {"event": "started", "task_id": 1, "worker_id": "owner", "at": float("nan")},
    ]
    for event in events:
        queue.path.write_bytes(initial + (json.dumps(event) + "\n").encode())
        with pytest.raises(ValueError, match="line 3"):
            TaskQueue.load(queue.path, repair=True)


def test_every_transition_is_flushed_and_fsynced_before_memory_changes(tmp_path, monkeypatch):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {1: ["a"]})
    original_fsync = task_queue_module.os.fsync
    observed = []

    def observe_fsync(fd):
        persisted_event = json.loads(queue.path.read_text().splitlines()[-1])["event"]
        observed.append((queue.status()[0]["state"], persisted_event))
        original_fsync(fd)

    monkeypatch.setattr(task_queue_module.os, "fsync", observe_fsync)
    queue.claim("worker")
    queue.started(1, "worker")
    queue.complete(1, "worker")
    assert observed == [("pending", "claimed"), ("claimed", "started"), ("started", "done")]


def test_initialization_and_tail_repair_are_fsynced(tmp_path, monkeypatch):
    original_fsync = task_queue_module.os.fsync
    synced = []

    def observe_fsync(fd):
        synced.append(task_queue_module.os.fstat(fd).st_size)
        original_fsync(fd)

    monkeypatch.setattr(task_queue_module.os, "fsync", observe_fsync)
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {1: ["a"]})
    complete_size = queue.path.stat().st_size
    assert synced == [complete_size]
    with queue.path.open("ab") as output:
        output.write(b'{"partial":')
    TaskQueue.load(queue.path, repair=True)
    assert synced == [complete_size, complete_size]


def test_failed_fsync_prevents_acknowledgement_and_further_mutations(tmp_path, monkeypatch):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {1: ["a"]})

    def fail_sync(fd):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(task_queue_module.os, "fsync", fail_sync)
    with pytest.raises(OSError, match="disk failure"):
        queue.claim("worker")
    assert queue.status()[0]["state"] == "pending"
    with pytest.raises(RuntimeError, match="reload"):
        queue.claim("worker")
    # A full append may survive a failed fsync. Replay is conservative, and an
    # unacknowledged claim is safely requeueable because it never started.
    replayed = TaskQueue.load(queue.path)
    assert replayed.status()[0]["state"] == "claimed"


def test_stale_loaded_owner_cannot_append_over_newer_events(tmp_path):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {1: ["a"]})
    stale = TaskQueue.load(queue.path)
    queue.claim("owner")
    before = queue.path.read_bytes()
    with pytest.raises(RuntimeError, match="changed outside"):
        stale.claim("stale-owner")
    assert queue.path.read_bytes() == before
    assert stale.status()[0]["state"] == "pending"


def test_create_refuses_existing_journal_and_load_refuses_missing_or_partial_initialization(tmp_path):
    path = tmp_path / "queue.jsonl"
    queue = TaskQueue.create(path, {1: ["a"]})
    queue.claim("worker")
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        TaskQueue.create(path, {2: ["b"]})
    assert path.read_bytes() == before
    with pytest.raises(FileNotFoundError):
        TaskQueue.load(tmp_path / "missing.jsonl")
    for content in (b"", b'{"event":"created",'):
        partial = tmp_path / "partial.jsonl"
        partial.write_bytes(content)
        with pytest.raises(ValueError, match="no complete initialization"):
            TaskQueue.load(partial, repair=True)
        assert partial.read_bytes() == content


@pytest.mark.parametrize("task_sites", [{True: ["a"]}, {1: [2]}, {"1": ["a"]}])
def test_create_validates_task_metadata_before_writing(tmp_path, task_sites):
    path = tmp_path / "queue.jsonl"
    with pytest.raises(ValueError):
        TaskQueue.create(path, task_sites)
    assert not path.exists()


@pytest.mark.parametrize("max_claims", [0, -1, 1.5, True])
def test_claim_rejects_invalid_limit(tmp_path, max_claims):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {})
    with pytest.raises(ValueError, match="positive integer"):
        queue.claim("worker", max_claims=max_claims)


@pytest.mark.parametrize("worker_id", ["", None, 1])
def test_claim_rejects_invalid_worker_id(tmp_path, worker_id):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {})
    with pytest.raises(ValueError, match="nonempty string"):
        queue.claim(worker_id)


def test_status_returns_independent_copies_and_empty_queue_replays(tmp_path):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {1: ["a"]})
    records = queue.status()
    records[0]["state"] = "done"
    records[0]["sites"].append("b")
    assert queue.status()[0]["state"] == "pending"
    assert queue.status()[0]["sites"] == ["a"]
    empty = TaskQueue.create(tmp_path / "empty.jsonl", {})
    assert empty.claim("worker") is None
    assert TaskQueue.load(empty.path).status() == []


@pytest.mark.parametrize("full_retry", [False, True])
def test_explicit_retry_keeps_attempt_history_and_replays_resume_metadata(tmp_path, full_retry):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {0: ["a"], 1: ["a"]})
    queue.claim("old")
    queue.started(0, "old")
    queue.fail(0, "old", "timed out")
    before = queue.path.read_bytes()

    queue.retry(0, full_retry=full_retry)
    row = queue.status()[0]
    assert row["state"] == "pending"
    assert row["worker_id"] is None
    assert row["retry_count"] == 1
    assert row["resume_worker_id"] == (None if full_retry else "old")
    assert row["full_retry"] is full_retry
    assert row["error"] is None
    assert row["claimed_at"] is row["started_at"] is row["finished_at"] is None
    assert queue.path.read_bytes().startswith(before)
    assert queue.claim("replacement") == 0
    queue.started(0, "replacement")
    queue.abandon_worker("replacement", "crashed")
    queue.retry(0)
    row = queue.status()[0]
    assert row["retry_count"] == 2
    assert row["resume_worker_id"] == "replacement"
    assert row["full_retry"] is False
    assert TaskQueue.load(queue.path).status() == queue.status()


@pytest.mark.parametrize("state", ["pending", "claimed", "started", "done"])
def test_retry_rejects_tasks_without_a_terminal_error(tmp_path, state):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {0: ["a"]})
    if state != "pending":
        queue.claim("worker")
    if state in {"started", "done"}:
        queue.started(0, "worker")
    if state == "done":
        queue.complete(0, "worker")
    before = queue.path.read_bytes()
    with pytest.raises(ValueError, match="not failed or interrupted"):
        queue.retry(0)
    assert queue.path.read_bytes() == before


def test_retry_requires_boolean_full_retry_and_rejects_unknown_task(tmp_path):
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {0: ["a"]})
    queue.claim("worker")
    queue.started(0, "worker")
    queue.fail(0, "worker", "failed")
    before = queue.path.read_bytes()
    with pytest.raises(ValueError, match="boolean"):
        queue.retry(0, full_retry=1)
    with pytest.raises(ValueError, match="Unknown task"):
        queue.retry(True)
    with pytest.raises(ValueError, match="Unknown task"):
        queue.retry(100)
    assert queue.path.read_bytes() == before
