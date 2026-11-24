"""Coordinator-owned FIFO scheduling and isolated worker process supervision."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import logging
import os
from pathlib import Path
import selectors
import signal
import socket
import subprocess
import time
import uuid

from webarena_pro_bgym.model_requests import write_run_usage
from webarena_pro_bgym.parallel import (
    _pid_is_running,
    build_worker_environment,
    reassign_worker_environment,
    reserve_worker_slot,
)
from webarena_pro_bgym.prewarm import cleanup_runtime_containers, container_prewarm_enabled
from webarena_pro_bgym.queue_client import MAX_MESSAGE_BYTES, REQUEST_FD_ENV, RESPONSE_FD_ENV
from webarena_pro_bgym.task_queue import TaskQueue

logger = logging.getLogger(__name__)


@contextmanager
def queue_directory_lock(root_dir: Path):
    """Refuse simultaneous coordinators, including resume of a live run."""
    root_dir.mkdir(parents=True, exist_ok=True)
    with (root_dir / "queue.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(f"A coordinator is already using {root_dir}") from error
        yield


def _write_metadata(path: Path, value) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _check_previous_workers(root_dir: Path) -> dict:
    path = root_dir / "queue_workers.json"
    if not path.exists():
        return {"workers": {}}
    previous = json.loads(path.read_text())
    if (not isinstance(previous, dict) or not isinstance(previous.get("workers"), dict)
            or any(type(pid) is not int or pid < 1 for pid in previous["workers"].values())):
        raise ValueError("Invalid saved worker roster")
    if previous.get("host") != socket.gethostname() and previous.get("workers"):
        raise ValueError("Resume on the original host to verify that its workers have stopped")
    # Never kill a process solely on the basis of a journal PID: it could have
    # been reused. Refusal is safe even in that case. Normal shutdown empties it.
    def group_exists(pid):
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    live = [pid for pid in previous.get("workers", {}).values()
            if _pid_is_running(pid) or group_exists(pid)]
    if live:
        raise ValueError(f"Previous workers are still running (PIDs {live}); stop them before resuming")
    return previous


def _recover_previous_runtimes(previous: dict, queue: TaskQueue) -> None:
    """Reacquire and clean orphaned slots before making their claims runnable."""
    owners = previous["workers"]
    if not owners:
        return
    runtime_slots = previous.get("runtime_slots")
    if (not isinstance(runtime_slots, dict) or set(runtime_slots) != set(owners)
            or any(not isinstance(slots, list) or not slots
                   or any(type(slot) is not int or slot < 0 for slot in slots)
                   for slots in runtime_slots.values())):
        raise ValueError(
            "Saved workers have no valid runtime slot metadata; clean their containers "
            "and remove the stale queue_workers.json roster before resuming"
        )
    slots = [slot for values in runtime_slots.values() for slot in values]
    if len(slots) != len(set(slots)):
        raise ValueError("Saved workers have overlapping runtime slots")
    sites = sorted({site for row in queue.status() for site in row["sites"]})
    reservations = []
    cleanup_started = False
    cleanup_succeeded = False
    try:
        # Claim every old slot first. If another run now owns one, refuse before
        # touching any container; PID reuse is already checked above.
        for slot in slots:
            reservations.append(reserve_worker_slot(sites=sites, worker_index=slot))
        cleanup_started = True
        for slot in reservations:
            env = build_worker_environment(sites=sites, worker_index=slot.worker_index, base_env=os.environ)
            env["WP_ACTIVE_RUNTIME_SLOT"] = str(slot.worker_index)
            cleanup_runtime_containers(sites=sites, env=env, strict=True)
        cleanup_succeeded = True
    finally:
        if not cleanup_started or cleanup_succeeded:
            for slot in reversed(reservations):
                slot.release()
        else:
            logger.error("Previous runtime cleanup failed; retaining its slot reservations")


def _stop_process_group(process: subprocess.Popen) -> None:
    # Reap a just-exited leader before probing/signalling its process group.
    # macOS can return EPERM for a group containing only its unreaped zombie.
    process.poll()
    def signal_group(signum):
        try:
            os.killpg(process.pid, signum)
        except PermissionError as error:
            # The leader can become a zombie between poll() and killpg().
            # Reap and retry, but never suppress a denial for a live group.
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                raise error
            os.killpg(process.pid, signum)

    try:
        signal_group(signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    try:
        signal_group(signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


@dataclass
class _Worker:
    process: subprocess.Popen
    worker_id: str
    request_fd: int
    response_fd: int
    environments: list[dict[str, str]]
    buffer: bytes = b""
    waiting: bool = False
    stopped: bool = False
    process_stopped: bool = False
    disconnected: bool = False
    disconnected_at: float | None = None
    queue_exhausted: bool = False
    protocol_error: str | None = None
    generation: int = 0
    consecutive_restarts: int = 0
    made_progress: bool = False


class _Coordinator:
    def __init__(
        self, queue: TaskQueue, workers: list[_Worker], sites: list[str], *,
        restart_worker: Callable[[_Worker], _Worker] | None = None,
        worker_stopped: Callable[[_Worker], None] | None = None,
        max_worker_restarts: int = 3,
    ):
        self.queue = queue
        self.workers = workers
        self.sites = sites
        self.selector = selectors.DefaultSelector()
        self.exit_codes = []
        self.restart_worker = restart_worker
        self.worker_stopped = worker_stopped
        self.max_worker_restarts = max_worker_restarts
        for worker in workers:
            self._register_worker(worker)

    def _register_worker(self, worker):
        os.set_blocking(worker.request_fd, False)
        os.set_blocking(worker.response_fd, False)
        self.selector.register(worker.request_fd, selectors.EVENT_READ, worker)

    def _reply(self, worker, **values):
        data = json.dumps({"ok": True, **values}).encode() + b"\n"
        try:
            if os.write(worker.response_fd, data) != len(data):
                raise BlockingIOError("Short pipe write")
        except (BrokenPipeError, BlockingIOError):
            # A worker may exit just after sending its final done message. The
            # transition remains durable even when it cannot receive the ACK.
            worker.disconnected = True
            worker.disconnected_at = time.monotonic()

    def _owned(self, worker):
        return [row for row in self.queue.status()
                if row["worker_id"] == worker.worker_id and row["state"] in {"claimed", "started"}]

    def _reply_claim(self, worker, task_id):
        metadata = {}
        if task_id is not None:
            row = next(row for row in self.queue.status() if row["task_id"] == task_id)
            metadata = {key: row[key] for key in ("retry_count", "full_retry", "resume_worker_id")}
        self._reply(worker, task_id=task_id, **metadata)

    def _message(self, worker, message):
        if not isinstance(message, dict) or worker.waiting:
            raise ValueError("Expected one queue request at a time")
        action = message.get("action")
        if action == "claim":
            lookahead = message.get("lookahead", False)
            if type(lookahead) is not bool:
                raise ValueError("lookahead must be a boolean")
            owned = self._owned(worker)
            if lookahead:
                if len(owned) != 1:
                    raise ValueError("Lookahead requires exactly one active claim")
                pending = sum(row["state"] == "pending" for row in self.queue.status())
                live = sum(not item.stopped for item in self.workers)
                # Leave work for startup/idle workers and a full batch at the
                # tail. This reduces avoidable tail imbalance without revoking
                # already-running prewarm jobs.
                task_id = self.queue.claim(worker.worker_id, max_claims=2) if pending > live else None
                self._reply_claim(worker, task_id)
            else:
                if owned:
                    raise ValueError("Active claim requested while worker still owns work")
                worker.waiting = True
            return
        task_id = message.get("task_id")
        if type(task_id) is not int:
            raise ValueError("task_id must be an integer")
        if action == "started":
            self.queue.started(task_id, worker.worker_id)
            worker.made_progress = True
        elif action == "done":
            self.queue.complete(task_id, worker.worker_id)
        elif action == "failed":
            error = message.get("error")
            if not isinstance(error, str):
                raise ValueError("failed requires an error string")
            self.queue.fail(task_id, worker.worker_id, error[:8192])
        else:
            raise ValueError(f"Unknown queue action: {action!r}")
        self._reply(worker)

    def _drain(self, worker):
        if worker.request_fd < 0:
            return
        try:
            while True:
                try:
                    data = os.read(worker.request_fd, MAX_MESSAGE_BYTES)
                except BlockingIOError:
                    break
                if not data:
                    worker.disconnected = True
                    worker.disconnected_at = time.monotonic()
                    self.selector.unregister(worker.request_fd)
                    os.close(worker.request_fd)
                    worker.request_fd = -1
                    if worker.buffer:
                        raise ValueError("Worker disconnected with a partial protocol message")
                    break
                worker.buffer += data
                while b"\n" in worker.buffer:
                    line, worker.buffer = worker.buffer.split(b"\n", 1)
                    if len(line) > MAX_MESSAGE_BYTES:
                        raise ValueError("Queue protocol message is too large")
                    self._message(worker, json.loads(line))
                if len(worker.buffer) > MAX_MESSAGE_BYTES:
                    raise ValueError("Queue protocol message is too large")
        except (ValueError, UnicodeError) as error:
            worker.protocol_error = str(error)
            worker.disconnected = True
            worker.disconnected_at = time.monotonic()
            logger.error("Queue protocol error from %s: %s", worker.worker_id, error)

    def _finish_worker(self, worker, reason):
        if worker.stopped:
            return
        failure = None
        try:
            # Drain even after poll says exited: done/started may be buffered.
            self._drain(worker)
        except BaseException as error:
            failure = error
        try:
            if not worker.process_stopped:
                _stop_process_group(worker.process)
                worker.process_stopped = True
        except BaseException as error:
            failure = failure or error
        try:
            if worker.process_stopped:
                restarting_early = (self.restart_worker and self.max_worker_restarts > 0
                                    and not worker.queue_exhausted
                                    and any(row["state"] == "pending" for row in self.queue.status()))
                if (worker.process.returncode or self._owned(worker)
                        or worker.protocol_error or failure or restarting_early):
                    for env in worker.environments:
                        cleanup_runtime_containers(sites=self.sites, env=env, strict=True)
                worker.stopped = True
                if self.worker_stopped:
                    self.worker_stopped(worker)
                # Containers and the entire old process group must stop before
                # claims return to FIFO or their runtime slots can be reused.
                self.queue.abandon_worker(worker.worker_id, reason)
        except BaseException as error:
            failure = failure or error
        finally:
            worker.waiting = False
            if worker.request_fd >= 0:
                try:
                    self.selector.unregister(worker.request_fd)
                except KeyError:
                    pass  # Startup/roster failure before selector registration.
                os.close(worker.request_fd)
                worker.request_fd = -1
            if worker.response_fd >= 0:
                os.close(worker.response_fd)
                worker.response_fd = -1
        self.exit_codes.append(worker.process.returncode or int(bool(worker.protocol_error)))
        if failure is not None:
            raise failure

    def close(self, reason="Coordinator stopped worker"):
        failure = None
        try:
            for worker in self.workers:
                try:
                    self._finish_worker(worker, reason)
                except BaseException as error:
                    failure = failure or error
        finally:
            self.selector.close()
        if failure is not None:
            raise failure

    def _serve_idle(self):
        for worker in self.workers:
            if worker.stopped or not worker.waiting:
                continue
            task_id = self.queue.claim(worker.worker_id)
            if task_id is not None:
                worker.waiting = False
                self._reply_claim(worker, task_id)
        # Idle workers stay available while another worker may return an
        # unstarted claim. They exit once every remaining task is terminal.
        has_work = any(row["state"] in {"pending", "claimed", "started"} for row in self.queue.status())
        if not has_work:
            for worker in self.workers:
                if worker.waiting and not worker.stopped:
                    worker.waiting = False
                    self._reply_claim(worker, None)
                    worker.queue_exhausted = not worker.disconnected

    def run(self):
        try:
            while any(not worker.stopped for worker in self.workers):
                for key, _ in self.selector.select(timeout=0.25):
                    self._drain(key.data)
                for worker in list(self.workers):
                    if worker.stopped:
                        continue
                    returncode = worker.process.poll()
                    # After the terminal reply, result aggregation and Python
                    # finalizers may legitimately outlast the disconnect grace
                    # period. Only unexpected disconnects need that deadline.
                    # Check exit first: a delayed parent poll must not turn an
                    # already-successful exit into a timeout failure.
                    expired = (returncode is None and not worker.queue_exhausted
                               and worker.disconnected_at is not None
                               and time.monotonic() - worker.disconnected_at > 5)
                    if returncode is not None or worker.protocol_error or expired:
                        if expired:
                            worker.protocol_error = "Worker disconnected without exiting"
                        self._finish_worker(worker, worker.protocol_error or "Worker exited before completion")
                        pending = any(row["state"] == "pending" for row in self.queue.status())
                        if pending and self.restart_worker:
                            # Started work leaves a terminal result on death, so
                            # it is real FIFO progress. Only startup/no-progress
                            # crashes can otherwise spin forever on one claim.
                            if (self.max_worker_restarts > 0 and
                                    (worker.made_progress or
                                     worker.consecutive_restarts < self.max_worker_restarts)):
                                replacement = self.restart_worker(worker)
                                self._register_worker(replacement)
                            else:
                                logger.error("Worker %s exhausted its restart budget", worker.worker_id)
                self._serve_idle()
        finally:
            self.close()


def run_queue_workers(
    *, task_sites: dict[int, list[str]], worker_count: int, root_dir: Path,
    command: list[str], resume: bool = False, prewarm: bool | None = None,
    resume_mode: str = "continue", max_worker_restarts: int = 3,
) -> int:
    """Own the FIFO, replacing dead workers without retrying their failed task.

    On explicit resume, ``continue`` retries terminal errors from checkpoints,
    ``fresh`` retries them from scratch, and ``incomplete`` skips them. Worker
    restart limits count consecutive deaths without a started task, per slot.
    """
    if not task_sites or worker_count < 1:
        raise ValueError("At least one task and worker are required")
    if resume_mode not in {"continue", "fresh", "incomplete"}:
        raise ValueError("resume_mode must be continue, fresh, or incomplete")
    if type(max_worker_restarts) is not int or max_worker_restarts < 0:
        raise ValueError("max_worker_restarts must be a nonnegative integer")
    root_dir = Path(root_dir).resolve()
    with queue_directory_lock(root_dir):
        queue_path = root_dir / "queue.jsonl"
        if resume:
            previous = _check_previous_workers(root_dir)
            queue = TaskQueue.load(queue_path, repair=True)
            _recover_previous_runtimes(previous, queue)
            if prewarm is None:
                prewarm = json.loads((root_dir / "queue_run.json").read_text()).get("prewarm")
            for owner in {row["worker_id"] for row in queue.status() if row["worker_id"]}:
                queue.abandon_worker(owner, "Recovered after previous coordinator stopped")
            _write_metadata(root_dir / "queue_workers.json", {
                "host": socket.gethostname(), "workers": {}, "runtime_slots": {},
            })
            if resume_mode != "incomplete":
                for row in queue.status():
                    if row["state"] in {"failed", "interrupted"}:
                        queue.retry(row["task_id"], full_retry=resume_mode == "fresh")
        else:
            queue = TaskQueue.create(queue_path, task_sites)
            _write_metadata(root_dir / "queue_run.json", {
                "command": command, "worker_count": worker_count,
                "prewarm": container_prewarm_enabled() if prewarm is None else prewarm,
                "max_worker_restarts": max_worker_restarts,
            })
        use_prewarm = container_prewarm_enabled() if prewarm is None else prewarm
        pending_count = sum(row["state"] == "pending" for row in queue.status())
        if not pending_count:
            logger.info("No pending or unstarted tasks remain in %s", root_dir)
            return int(any(row["state"] != "done" for row in queue.status()))
        sites = sorted({site for row in queue.status() for site in row["sites"]})
        workers = []
        reservations = []
        coordinator = None
        session = uuid.uuid4().hex[:8]
        worker_roster = {"host": socket.gethostname(), "workers": {}, "runtime_slots": {}}
        roster_path = root_dir / "queue_workers.json"

        def launch_worker(environments, *, generation=0, consecutive_restarts=0):
            environments = [dict(env) for env in environments]
            env = environments[0]
            worker_id = f"worker-{env['WP_ACTIVE_RUNTIME_SLOT']}-r{generation}-{session}"
            worker_dir = root_dir / "workers" / worker_id
            worker_dir.mkdir(parents=True, exist_ok=False)
            cmd = [*command, "--study-dir", str(worker_dir),
                   "--task-queue", str(queue_path), "--queue-worker", worker_id]
            request_read, request_write = os.pipe()
            response_read, response_write = os.pipe()
            env[REQUEST_FD_ENV] = str(request_write)
            env[RESPONSE_FD_ENV] = str(response_read)
            try:
                with (worker_dir / "worker.log").open("w", encoding="utf-8") as log:
                    process = subprocess.Popen(
                        cmd, env=env, stdout=log, stderr=subprocess.STDOUT,
                        start_new_session=True, pass_fds=(request_write, response_read),
                    )
            except BaseException:
                os.close(request_read)
                os.close(response_write)
                raise
            finally:
                os.close(request_write)
                os.close(response_read)
            worker = _Worker(
                process, worker_id, request_read, response_write, environments,
                generation=generation, consecutive_restarts=consecutive_restarts,
            )
            workers.append(worker)
            worker_roster["workers"][worker_id] = process.pid
            worker_roster["runtime_slots"][worker_id] = [
                int(item["WP_ACTIVE_RUNTIME_SLOT"]) for item in environments
            ]
            _write_metadata(roster_path, worker_roster)
            logger.info("Queue worker %s started; logs at %s", worker_id, worker_dir / "worker.log")
            return worker

        def restart_worker(worker):
            return launch_worker(
                worker.environments, generation=worker.generation + 1,
                consecutive_restarts=0 if worker.made_progress else worker.consecutive_restarts + 1,
            )

        def worker_stopped(worker):
            worker_roster["workers"].pop(worker.worker_id, None)
            worker_roster["runtime_slots"].pop(worker.worker_id, None)
            _write_metadata(roster_path, worker_roster)

        def interrupted(signum, frame):
            raise KeyboardInterrupt(f"Coordinator received signal {signum}")

        previous_term = signal.signal(signal.SIGTERM, interrupted)
        try:
            for _ in range(min(worker_count, pending_count)):
                reservations.append(reserve_worker_slot(sites=sites))
            for slot in list(reservations):
                env = build_worker_environment(sites=sites, worker_index=slot.worker_index, base_env=os.environ)
                env["WP_ACTIVE_RUNTIME_SLOT"] = str(slot.worker_index)
                env["WP_PREWARM_CONTAINERS"] = "1" if use_prewarm else "0"
                env.pop("WP_PREWARMED_TASK_ID", None)
                env.pop("WP_QUEUE_STANDBY_SLOT", None)
                environments = [env]
                if pending_count > 1 and use_prewarm:
                    try:
                        standby = reserve_worker_slot(sites=sites)
                    except RuntimeError:
                        env["WP_PREWARM_CONTAINERS"] = "0"
                    else:
                        reservations.append(standby)
                        env["WP_QUEUE_STANDBY_SLOT"] = str(standby.worker_index)
                        environments.append(reassign_worker_environment(
                            sites=sites, from_worker_index=slot.worker_index,
                            to_worker_index=standby.worker_index, base_env=env,
                        ))
                launch_worker(environments)
            coordinator = _Coordinator(
                queue, workers, sites, restart_worker=restart_worker,
                worker_stopped=worker_stopped, max_worker_restarts=max_worker_restarts,
            )
            coordinator.run()
        finally:
            try:
                if coordinator is None and workers:
                    # A startup failure must close pipes and kill every worker
                    # before any of its unstarted claims can be recovered.
                    coordinator = _Coordinator(queue, workers, sites)
                    coordinator.close("Coordinator startup failed")
            finally:
                try:
                    if all(worker.stopped for worker in workers):
                        try:
                            _write_metadata(roster_path, {"host": socket.gethostname(), "workers": {}})
                        finally:
                            for slot in reversed(reservations):
                                slot.release()
                        write_run_usage(root_dir)
                    else:
                        logger.error("Some worker groups could not be stopped; retaining their roster and reservations")
                finally:
                    signal.signal(signal.SIGTERM, previous_term)
        unfinished = [row for row in queue.status() if row["state"] != "done"]
        if unfinished:
            logger.error("%d tasks failed, were interrupted or remain pending; inspect %s", len(unfinished), queue_path)
        # Recovered startup failures should not fail an otherwise complete run.
        # A started task lost with its worker remains failed/interrupted above.
        return int(bool(unfinished))
