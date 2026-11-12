"""Coordinator-owned FIFO scheduling with a durable JSON-lines journal.

Only the coordinator mutates this queue. Workers exchange messages with it and
never open the journal. Claims become unsafe to retry only after ``started``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
import os
from pathlib import Path
import time


class TaskQueue:
    """Keep scheduling state in memory and fsync each transition before use.

    Use :meth:`create` for a new run and :meth:`load` to inspect or resume a run.
    A resumed coordinator must stop old workers before abandoning their claims.
    One coordinator owns the journal at a time; this class is not an IPC API.
    """

    @classmethod
    def create(
        cls, path: str | Path, task_sites: Mapping[int, Sequence[str]]
    ) -> TaskQueue:
        """Create an exclusive journal with tasks in mapping iteration order."""
        event = {
            "event": "created",
            "version": 1,
            "tasks": [
                {"task_id": task_id, "position": position, "sites": list(dict.fromkeys(sites))}
                for position, (task_id, sites) in enumerate(task_sites.items())
            ],
        }
        queue = cls._initialize(Path(path).resolve(), event)
        queue.path.parent.mkdir(parents=True, exist_ok=True)
        data = cls._encode(event)
        with queue.path.open("xb") as journal:
            journal.write(data)
            journal.flush()
            os.fsync(journal.fileno())
        queue._journal_size = len(data)
        return queue

    @classmethod
    def load(cls, path: str | Path, *, repair: bool = False) -> TaskQueue:
        """Replay complete events without changing task states.

        An unterminated final line is ignored. By default it is left untouched
        and the returned queue cannot write. ``repair=True`` truncates that
        incomplete tail and fsyncs the repair before allowing resumed writes.
        Malformed complete lines always raise ValueError, even with repair.
        """
        path = Path(path).resolve()
        data = path.read_bytes()
        complete_size = data.rfind(b"\n") + 1
        lines = data[:complete_size].splitlines()
        if not lines:
            raise ValueError(f"Queue journal {path} has no complete initialization event")
        queue = None
        for line_number, line in enumerate(lines, 1):
            try:
                event = json.loads(line)
                if line_number == 1:
                    queue = cls._initialize(path, event)
                else:
                    queue._records.update(queue._changes(event))
            except (ValueError, TypeError, KeyError, OverflowError) as error:
                raise ValueError(
                    f"Invalid queue journal {path} at line {line_number}: {error}"
                ) from error
        queue._journal_size = complete_size
        if complete_size != len(data):
            if repair:
                with path.open("r+b") as journal:
                    journal.truncate(complete_size)
                    journal.flush()
                    os.fsync(journal.fileno())
            else:
                queue._write_blocked = (
                    "Queue journal has an incomplete tail; use TaskQueue.load(path, repair=True) "
                    "before resuming writes"
                )
        return queue

    @classmethod
    def _initialize(cls, path: Path, event: dict) -> TaskQueue:
        if not isinstance(event, dict) or set(event) != {"event", "version", "tasks"}:
            raise ValueError("Expected a queue initialization event")
        if event["event"] != "created" or type(event["version"]) is not int or event["version"] != 1:
            raise ValueError("Unsupported queue journal version or initialization event")
        if not isinstance(event["tasks"], list):
            raise ValueError("Initialization tasks must be a list")
        queue = cls()
        queue.path = path
        queue._records = {}
        queue._journal_size = 0
        queue._write_blocked = None
        for position, task in enumerate(event["tasks"]):
            if not isinstance(task, dict) or set(task) != {"task_id", "position", "sites"}:
                raise ValueError("Invalid task metadata")
            task_id, sites = task["task_id"], task["sites"]
            if type(task_id) is not int or task_id in queue._records:
                raise ValueError("Task IDs must be unique integers")
            if type(task["position"]) is not int or task["position"] != position:
                raise ValueError("Task positions must preserve the original FIFO order")
            if not isinstance(sites, list) or any(not isinstance(site, str) for site in sites):
                raise ValueError("Task sites must be a list of strings")
            if len(set(sites)) != len(sites):
                raise ValueError("Task sites must not contain duplicates")
            queue._records[task_id] = {
                "task_id": task_id,
                "sites": list(sites),
                "state": "pending",
                "worker_id": None,
                "error": None,
                "claimed_at": None,
                "started_at": None,
                "finished_at": None,
                "retry_count": 0,
                "resume_worker_id": None,
                "full_retry": False,
            }
        return queue

    @staticmethod
    def _encode(event: dict) -> bytes:
        return (json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")

    @staticmethod
    def _validate_worker(worker_id: str) -> None:
        if not isinstance(worker_id, str) or not worker_id:
            raise ValueError("worker_id must be a nonempty string")

    def _ensure_writable(self) -> None:
        if self._write_blocked:
            raise RuntimeError(self._write_blocked)

    def _record(self, event: dict) -> None:
        self._ensure_writable()
        changes = self._changes(event)
        data = self._encode(event)
        try:
            with self.path.open("r+b") as journal:
                if journal.seek(0, os.SEEK_END) != self._journal_size:
                    raise RuntimeError("Queue journal changed outside its coordinator; reload before writing")
                journal.write(data)
                journal.flush()
                os.fsync(journal.fileno())
        except BaseException:
            self._write_blocked = "Queue journal write failed; reload with repair=True before resuming"
            raise
        # Do not grant a task or acknowledge its start before the journal syncs.
        self._journal_size += len(data)
        self._records.update(changes)

    def _changes(self, event: dict) -> dict[int, dict]:
        if not isinstance(event, dict):
            raise ValueError("Transition event must be an object")
        kind = event.get("event")
        if kind not in {"claimed", "started", "done", "failed", "abandoned", "retry"}:
            raise ValueError(f"Unknown queue transition {kind!r}")
        fields = {"event", "worker_id", "at"}
        fields.add("task_ids" if kind == "abandoned" else "task_id")
        if kind in {"failed", "abandoned"}:
            fields.add("error")
        if kind == "retry":
            fields.add("full_retry")
        if set(event) != fields:
            raise ValueError(f"Invalid fields for {kind} transition")
        worker_id = event["worker_id"]
        self._validate_worker(worker_id)
        timestamp = event["at"]
        if type(timestamp) not in {int, float} or not math.isfinite(timestamp):
            raise ValueError("Transition timestamp must be finite")
        if kind in {"failed", "abandoned"} and not isinstance(event["error"], str):
            raise ValueError("Transition error must be a string")
        if kind == "abandoned":
            if not isinstance(event["task_ids"], list) or any(
                type(task_id) is not int for task_id in event["task_ids"]
            ):
                raise ValueError("Abandoned task IDs must be a list of integers")
            owned = [task_id for task_id, row in self._records.items()
                     if row["worker_id"] == worker_id and row["state"] in {"claimed", "started"}]
            if event["task_ids"] != owned or not owned:
                raise ValueError("Abandoned task IDs must match the worker's outstanding claims")
            changes = {}
            for task_id in owned:
                row = self._records[task_id]
                if row["state"] == "claimed":
                    changes[task_id] = row | {
                        "state": "pending", "worker_id": None, "error": None,
                        "claimed_at": None, "started_at": None, "finished_at": None,
                    }
                else:
                    changes[task_id] = row | {
                        "state": "interrupted", "error": event["error"], "finished_at": timestamp,
                    }
            return changes
        task_id = event["task_id"]
        if type(task_id) is not int or task_id not in self._records:
            raise ValueError(f"Unknown task ID {task_id!r}")
        row = self._records[task_id]
        if kind == "retry":
            if type(event["full_retry"]) is not bool:
                raise ValueError("full_retry must be a boolean")
            if row["state"] not in {"failed", "interrupted"} or row["worker_id"] != worker_id:
                raise ValueError(f"Task {task_id} is not failed or interrupted by worker {worker_id!r}")
            return {task_id: row | {
                "state": "pending", "worker_id": None, "error": None,
                "claimed_at": None, "started_at": None, "finished_at": None,
                "retry_count": row["retry_count"] + 1,
                "resume_worker_id": None if event["full_retry"] else worker_id,
                "full_retry": event["full_retry"],
            }}
        expected = "pending" if kind == "claimed" else "claimed" if kind == "started" else "started"
        if row["state"] != expected or (kind != "claimed" and row["worker_id"] != worker_id):
            raise ValueError(f"Task {task_id} is not {expected} by worker {worker_id!r}")
        updates = {"state": kind}
        if kind == "claimed":
            updates.update(worker_id=worker_id, claimed_at=timestamp)
        elif kind == "started":
            updates["started_at"] = timestamp
        else:
            updates.update(finished_at=timestamp, error=event.get("error"))
        return {task_id: row | updates}

    def claim(self, worker_id: str, max_claims: int = 1) -> int | None:
        """Claim the oldest pending task, counting started work toward capacity."""
        self._ensure_writable()
        self._validate_worker(worker_id)
        if type(max_claims) is not int or max_claims < 1:
            raise ValueError("max_claims must be a positive integer")
        active = sum(row["worker_id"] == worker_id and row["state"] in {"claimed", "started"}
                     for row in self._records.values())
        if active >= max_claims:
            return None
        for task_id, row in self._records.items():
            if row["state"] == "pending":
                self._record({"event": "claimed", "task_id": task_id,
                              "worker_id": worker_id, "at": time.time()})
                return task_id
        return None

    def started(self, task_id: int, worker_id: str) -> None:
        """Durably acknowledge that an owned claim is about to execute."""
        self._record({"event": "started", "task_id": task_id,
                      "worker_id": worker_id, "at": time.time()})

    def complete(self, task_id: int, worker_id: str) -> None:
        """Mark an owned, started task done."""
        self._record({"event": "done", "task_id": task_id,
                      "worker_id": worker_id, "at": time.time()})

    def fail(self, task_id: int, worker_id: str, error: str) -> None:
        """Record a started task failure without retrying it on another worker."""
        self._record({"event": "failed", "task_id": task_id, "worker_id": worker_id,
                      "error": error, "at": time.time()})

    def abandon_worker(self, worker_id: str, error: str) -> int:
        """Requeue unstarted claims and interrupt started tasks atomically."""
        self._ensure_writable()
        self._validate_worker(worker_id)
        if not isinstance(error, str):
            raise ValueError("Transition error must be a string")
        task_ids = [task_id for task_id, row in self._records.items()
                    if row["worker_id"] == worker_id and row["state"] in {"claimed", "started"}]
        if task_ids:
            self._record({"event": "abandoned", "task_ids": task_ids,
                          "worker_id": worker_id, "error": error, "at": time.time()})
        return len(task_ids)

    def retry(self, task_id: int, *, full_retry: bool = False) -> None:
        """Explicitly retry a terminal error, retaining its durable attempt history.

        Coordinators call this once when the user resumes a run, never when a
        replacement worker starts. A reproducible failure therefore cannot
        monopolize the queue. Checkpoint recovery is the worker's responsibility.
        """
        if type(task_id) is not int or task_id not in self._records:
            raise ValueError(f"Unknown task ID {task_id!r}")
        row = self._records[task_id]
        if row["state"] not in {"failed", "interrupted"}:
            raise ValueError(f"Task {task_id} is not failed or interrupted")
        self._record({"event": "retry", "task_id": task_id, "worker_id": row["worker_id"],
                      "full_retry": full_retry, "at": time.time()})

    def status(self) -> list[dict]:
        """Return independent task records in their original FIFO order."""
        return [row | {"sites": list(row["sites"])} for row in self._records.values()]
