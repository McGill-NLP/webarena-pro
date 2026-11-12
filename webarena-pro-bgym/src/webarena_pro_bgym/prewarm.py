"""One-task-ahead website container preparation for sequential workers."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


logger = logging.getLogger(__name__)

PREWARM_CONTAINERS_ENV_VAR = "WP_PREWARM_CONTAINERS"
PREWARMED_TASK_ENV_VAR = "WP_PREWARMED_TASK_ID"
ASSIGNED_RUN_SLOT_ENV_VAR = "WP_ASSIGNED_RUN_SLOT"
PARALLEL_WORKER_INDEX_ENV_VAR = "WP_PARALLEL_WORKER_INDEX"
ACTIVE_RUNTIME_SLOT_ENV_VAR = "WP_ACTIVE_RUNTIME_SLOT"
_FALSEY_VALUES = {"0", "false", "no", "off"}


def container_prewarm_enabled() -> bool:
    raw = os.environ.get(PREWARM_CONTAINERS_ENV_VAR)
    return raw is None or raw.strip().lower() not in _FALSEY_VALUES


def assigned_runtime_slot(env: Mapping[str, str] | None = None) -> int | None:
    target_env = os.environ if env is None else env
    raw = (
        target_env.get(ACTIVE_RUNTIME_SLOT_ENV_VAR)
        or target_env.get(ASSIGNED_RUN_SLOT_ENV_VAR)
        or target_env.get(PARALLEL_WORKER_INDEX_ENV_VAR)
    )
    if raw in {None, ""}:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("Ignoring invalid runtime slot index %r", raw)
        return None


@dataclass
class ContainerPrewarmJob:
    process: subprocess.Popen
    task_id: str
    sites: tuple[str, ...]
    runtime_slot: int

    def wait(self) -> bool:
        exit_code = self.process.wait()
        if exit_code == 0:
            logger.info(
                "Prewarmed task %s on runtime slot w%d; it is ready to launch.",
                self.task_id,
                self.runtime_slot,
            )
            return True

        logger.warning(
            "Container prewarm for task %s on runtime slot w%d exited with code "
            "%d; the task will reset that slot synchronously.",
            self.task_id,
            self.runtime_slot,
            exit_code,
        )
        return False

    def cancel(self) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def launch_container_prewarm(
    *,
    sites: Sequence[str],
    task_id: str,
    runtime_slot: int,
    env: Mapping[str, str],
) -> ContainerPrewarmJob:
    target_sites = tuple(dict.fromkeys(str(site) for site in sites))
    if not target_sites:
        raise ValueError("sites must contain at least one website")

    logger.info(
        "Starting container prewarm for next task %s on runtime slot w%d: %s",
        task_id,
        runtime_slot,
        ", ".join(target_sites),
    )
    command = [
        sys.executable,
        "-m",
        "webarena_pro_bgym.prewarm",
        "prepare",
        "--task-id",
        str(task_id),
    ]
    for site in target_sites:
        command.extend(("--site", site))

    process = subprocess.Popen(command, env=dict(env))
    return ContainerPrewarmJob(
        process=process,
        task_id=str(task_id),
        sites=target_sites,
        runtime_slot=int(runtime_slot),
    )


def cleanup_runtime_containers(
    *,
    sites: Sequence[str],
    env: Mapping[str, str],
    strict: bool = False,
) -> None:
    target_sites = tuple(dict.fromkeys(str(site) for site in sites))
    if not target_sites:
        return

    command = [sys.executable, "-m", "webarena_pro_bgym.prewarm", "stop"]
    if strict:
        command.append("--strict")
    for site in target_sites:
        command.extend(("--site", site))
    try:
        result = subprocess.run(
            command,
            env=dict(env),
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        if strict:
            raise
        logger.exception("Failed to clean up prewarm runtime containers")
        return
    if result.returncode != 0:
        if strict:
            raise RuntimeError(f"Prewarm runtime cleanup exited with code {result.returncode}")
        logger.warning(
            "Prewarm runtime cleanup exited with code %d", result.returncode
        )


def prepare_sites(sites: Sequence[str], *, task_id: str) -> None:
    from webarena_pro_core.state_reset import reset_site

    for site in dict.fromkeys(str(site) for site in sites):
        logger.info("[prewarm task=%s] preparing %s", task_id, site)
        reset_site(site)
        logger.info("[prewarm task=%s] %s is ready", task_id, site)


def stop_sites(sites: Sequence[str], *, strict: bool = False) -> None:
    from webarena_pro_core.state_reset import stop_site_container

    for site in dict.fromkeys(str(site) for site in sites):
        try:
            stop_site_container(site)
        except Exception:
            if strict:
                raise
            logger.exception("Failed to stop prewarm container for %s", site)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--task-id", required=True)
    prepare_parser.add_argument("--site", action="append", required=True)

    stop_parser = subparsers.add_parser("stop")
    stop_parser.add_argument("--site", action="append", required=True)
    stop_parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    args = _build_parser().parse_args(argv)
    if args.action == "prepare":
        prepare_sites(args.site, task_id=args.task_id)
    else:
        stop_sites(args.site, strict=args.strict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
