"""Host-local, crash-safe coordination for shared Docker runtime work."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)
_held = threading.local()
# Keep all descriptors visible to the at-fork hook, including other threads'.
_descriptors: set[int] = set()


def _after_fork() -> None:
    for descriptor in _descriptors:
        os.close(descriptor)
    _descriptors.clear()
    _held.locks = set()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


def positive_setting(name: str, default: float) -> float:
    value = os.environ.get(name, str(default))
    try:
        parsed = float(value)
    except ValueError:
        parsed = 0
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{name} must be a finite positive number; got {value!r}")
    return parsed


def docker_timeout() -> float:
    return positive_setting("WP_DOCKER_TIMEOUT_SECONDS", 300)


def docker_lifecycle_slots() -> int:
    value = positive_setting("WP_DOCKER_LIFECYCLE_SLOTS", 4)
    if not value.is_integer():
        raise ValueError("WP_DOCKER_LIFECYCLE_SLOTS must be a positive integer")
    return int(value)


def _try_lock(descriptor: int) -> bool:
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
    else:
        import fcntl

        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
    return True


@contextmanager
def runtime_lock(name: str, *, slots: int = 1):
    """Acquire an OS-owned slot; nested calls in one thread reuse its permit.

    Lock files are never removed: deleting a locked inode would let a new
    process bypass its owner. The OS releases permits on close/process death.
    """
    user = str(os.getuid()) if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")
    root = Path(os.environ.get(
        "WP_RUNTIME_LOCK_DIR", str(Path(tempfile.gettempdir()) / f"webarena-pro-runtime-{user}")
    ))
    root.mkdir(parents=True, exist_ok=True)
    key = str(root.resolve()), name
    held = getattr(_held, "locks", None)
    if held is None:
        held = _held.locks = set()
    if key in held:
        yield
        return

    timeout = positive_setting("WP_DOCKER_LOCK_TIMEOUT_SECONDS", 1200)
    started = time.monotonic()
    deadline = started + timeout
    digest = hashlib.sha256(name.encode()).hexdigest()[:24]
    descriptor = None
    while descriptor is None:
        for slot in range(slots):
            candidate = os.open(root / f"{digest}-{slot}.lock", os.O_CREAT | os.O_RDWR, 0o600)
            _descriptors.add(candidate)
            try:
                if _try_lock(candidate):
                    descriptor = candidate
                    break
            except BaseException:
                _descriptors.discard(candidate)
                os.close(candidate)
                raise
            _descriptors.discard(candidate)
            os.close(candidate)
        if descriptor is not None:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Timed out after {timeout:g}s waiting for runtime lock {name!r} "
                f"({slots} slot(s), directory={root}); "
                "configure WP_DOCKER_LOCK_TIMEOUT_SECONDS or WP_DOCKER_LIFECYCLE_SLOTS"
            )
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))

    held.add(key)
    owner = os.getpid()
    logger.debug("Acquired runtime lock %s after %.2fs", name, time.monotonic() - started)
    try:
        yield
    finally:
        # A child that returns through this inherited context no longer owns
        # the descriptor: the at-fork hook already closed its copy.
        if os.getpid() == owner:
            held.remove(key)
            _descriptors.discard(descriptor)
            os.close(descriptor)


@contextmanager
def docker_lifecycle_slot():
    with runtime_lock("docker-lifecycle", slots=docker_lifecycle_slots()):
        yield
