"""Framework-neutral verifier registry for evaluation sidecars."""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping

from webarena_pro_core.eval.protocol import (
    EvaluationStepRecord,
    StepVerifier,
    validate_rubric_step_record,
)

logger = logging.getLogger(__name__)

_SENTINEL = object()


@dataclass
class _WorkerHandle:
    queue: queue.Queue
    thread: threading.Thread
    busy: threading.Event


_lock = threading.Lock()
_registry: dict[StepVerifier, _WorkerHandle] = {}


def register_step_verifier(
    verifier: StepVerifier,
    *,
    queue_maxsize: int = 64,
) -> None:
    """Register a verifier sidecar and start its worker thread."""

    with _lock:
        if verifier in _registry:
            return
        handle = _WorkerHandle(
            queue=queue.Queue(maxsize=queue_maxsize),
            thread=None,  # type: ignore[arg-type]
            busy=threading.Event(),
        )
        thread = threading.Thread(
            target=_worker_loop,
            args=(verifier, handle),
            daemon=True,
            name=f"eval-verifier-{type(verifier).__name__}",
        )
        handle.thread = thread
        _registry[verifier] = handle
        thread.start()


def unregister_step_verifier(
    verifier: StepVerifier,
    *,
    timeout: float | None = 30.0,
) -> None:
    """Stop a verifier worker. Silent no-op if the verifier is not registered."""

    with _lock:
        handle = _registry.pop(verifier, None)
    if handle is None:
        return
    handle.queue.put(_SENTINEL)
    handle.thread.join(timeout)


def registered_step_verifiers() -> list[StepVerifier]:
    """Return a snapshot of registered verifier instances."""

    with _lock:
        return list(_registry)


def dispatch_step_record(
    record: Mapping[str, Any],
    *,
    validate: bool = True,
) -> None:
    """Enqueue a normalized evaluation step for every registered verifier."""

    with _lock:
        if not _registry:
            return
        handles = list(_registry.items())

    if validate:
        validate_rubric_step_record(record)

    # Detach from mutable runner-owned dicts, but do not deep-copy screenshot
    # objects. Screenshot arrays/images are large and verifier implementations
    # can copy them if they mutate pixels.
    for verifier, handle in handles:
        detached: EvaluationStepRecord = dict(record)  # type: ignore[assignment]
        try:
            handle.queue.put_nowait(detached)
        except queue.Full:
            logger.warning(
                "verifier %s queue full at step=%s; dropping record",
                type(verifier).__name__,
                detached.get("step"),
            )


def drain_step_verifiers(timeout: float | None = None) -> None:
    """Block until every registered verifier has processed queued records."""

    with _lock:
        handles = list(_registry.values())
    deadline = None if timeout is None else time.monotonic() + timeout

    for handle in handles:
        if deadline is None:
            handle.queue.join()
        else:
            while time.monotonic() < deadline:
                if handle.queue.unfinished_tasks == 0:
                    break
                time.sleep(0.02)
        while handle.busy.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                break
            time.sleep(0.01)


def _worker_loop(verifier: StepVerifier, handle: _WorkerHandle) -> None:
    while True:
        record = handle.queue.get()
        try:
            if record is _SENTINEL:
                return
            handle.busy.set()
            try:
                verifier.on_agent_step_end(record)  # type: ignore[arg-type]
            except Exception:
                logger.warning(
                    "verifier %s raised in on_agent_step_end at step=%s; continuing",
                    type(verifier).__name__,
                    record.get("step") if isinstance(record, dict) else "?",
                    exc_info=True,
                )
            finally:
                handle.busy.clear()
        finally:
            handle.queue.task_done()


# More explicit alias for readers who think in evaluator events rather than
# runner steps.
dispatch_evaluation_step = dispatch_step_record
