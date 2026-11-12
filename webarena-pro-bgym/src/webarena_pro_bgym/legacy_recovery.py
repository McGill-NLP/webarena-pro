"""Migrate legacy studies into supervised FIFO execution without altering them."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import logging
import os
from pathlib import Path
import pickle
import re
import shutil
import sys
import tempfile

from webarena_pro_bgym.queue_runner import (
    _write_metadata,
    queue_directory_lock,
    run_queue_workers,
)
from webarena_pro_bgym.study import WebArenaProStudy
from webarena_pro_bgym.task_queue import TaskQueue

logger = logging.getLogger(__name__)


def _task_id(experiment) -> int:
    return int(experiment.env_args.task_name.rsplit(".", 1)[-1])


def _legacy_results(root: Path) -> dict[int, Path]:
    """Find the latest visible attempt, including an interrupted result stub."""
    results = {}
    for path in sorted(root.glob("**/exp_args.pkl"),
                       key=lambda path: (path.stat().st_mtime_ns, str(path))):
        if any(part.startswith(("_", ".")) for part in path.relative_to(root).parts):
            continue
        match = re.search(r"webarena-pro-bgym\.(\d+)(?:_|$)", path.parent.name)
        if match:
            results[int(match[1])] = path.parent
    return results


def _fresh_experiments(study, max_steps=None):
    for experiment in study.exp_args_list:
        experiment.exp_dir = None
        experiment.is_dummy = False
        experiment.status = "incomplete"
        experiment.err_msg = None
        experiment.stack_trace = None
        experiment.worker_fatal_error = None
        # Legacy studies may themselves have been saved by a newer runner.
        # Their checkpoints cannot belong to this independently owned queue.
        for name in ("checkpoint_path", "resume_requested", "resume_from_start"):
            experiment.__dict__.pop(name, None)
        if max_steps is not None:
            experiment.env_args.max_steps = max_steps


def _bootstrap(study, root: Path, *, command, max_steps, n_jobs, max_worker_restarts):
    """Atomically expose a complete queue and its original task definitions."""
    source = Path(study.dir).resolve()
    with queue_directory_lock(source):
        if root.exists():
            raise ValueError(f"Recovery directory already exists: {root}; resume that directory")
        temporary = Path(tempfile.mkdtemp(prefix="_recovery-building-", dir=source))
        try:
            snapshot = deepcopy(study)
            snapshot.dir = temporary
            _fresh_experiments(snapshot, max_steps)
            task_sites = {}
            for experiment in snapshot.exp_args_list:
                task_id = _task_id(experiment)
                if task_id in task_sites:
                    raise ValueError("Legacy recovery requires one experiment per task ID")
                config = experiment.env_args.task_config
                task_sites[task_id] = list(getattr(config, "sites", None) or [config.website])
            if not task_sites:
                raise ValueError("The legacy study contains no tasks")
            snapshot.save()
            old_results = _legacy_results(source)
            queue = TaskQueue.create(temporary / "queue.jsonl", task_sites)
            # Claim all entries in original FIFO order. Unfinished legacy tasks
            # are returned as pending only after the historical outcomes exist.
            for task_id in task_sites:
                assert queue.claim("legacy", max_claims=len(task_sites)) == task_id
                previous = old_results.get(task_id)
                if previous is None:
                    continue
                destination = temporary / "workers" / "legacy" / previous.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                # Same-filesystem hardlinks preserve full old traces without
                # duplicating screenshots/video or writing through the links.
                shutil.copytree(previous, destination, copy_function=os.link)
                summary_path = previous / "summary_info.json"
                if not summary_path.exists():
                    continue
                summary = json.loads(summary_path.read_text())
                if not isinstance(summary, dict):
                    raise ValueError(f"Invalid legacy task summary: {summary_path}")
                queue.started(task_id, "legacy")
                if summary.get("err_msg"):
                    queue.fail(task_id, "legacy", str(summary["err_msg"]))
                else:
                    queue.complete(task_id, "legacy")
            queue.abandon_worker("legacy", "Legacy tasks without a completed summary")
            _write_metadata(temporary / "queue_run.json", {
                "command": command, "worker_count": n_jobs,
                "prewarm": False, "max_worker_restarts": max_worker_restarts,
            })
            temporary.rename(root)
            return task_sites
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise


def resume_legacy_study(study, args) -> int:
    """Explicit full retry migrates once; future resumes use its checkpoints."""
    from webarena_pro_bgym.run_eval_cli import (
        aggregate_parallel_results,
        ensure_docker_running,
    )

    if getattr(args, "no_reset_per_task", False):
        logger.error("Supervised legacy recovery requires per-task reset")
        return 2
    if not ensure_docker_running():
        return 1
    root = Path(study.dir).resolve() / "_recovery"
    restart_limit = getattr(args, "max_worker_restarts", None)
    restart_limit = 3 if restart_limit is None else restart_limit
    command = [sys.executable, str(Path(__file__).resolve()),
               "--source-study", str(root), "--n-relaunch", str(args.n_relaunch)]
    if args.max_steps is not None:
        command.extend(["--max-steps", str(args.max_steps)])
    try:
        task_sites = _bootstrap(
            study, root, command=command, max_steps=args.max_steps,
            n_jobs=args.n_jobs, max_worker_restarts=restart_limit,
        )
        logger.info("Migrated legacy study to %s; original results are preserved", root)
        result = run_queue_workers(
            task_sites=task_sites, worker_count=args.n_jobs, root_dir=root,
            command=command, resume=True, prewarm=False,
            resume_mode="incomplete" if args.incomplete_only else "fresh",
            max_worker_restarts=restart_limit,
        )
        aggregate_parallel_results(site="legacy recovery", root_dir=root)
        if any(root.glob("**/summary_info.json")):
            WebArenaProStudy.load(root).get_results(suffix="recovery")
        return result
    except KeyboardInterrupt:
        logger.warning("Recovery interrupted; resume with --resume-study %s", root)
        return 130
    except (OSError, ValueError, RuntimeError, pickle.PickleError):
        logger.exception("Legacy recovery failed; existing results remain at %s", study.dir)
        return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Supervised legacy study worker")
    parser.add_argument("--source-study", type=Path, required=True)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--task-queue", type=Path, required=True)
    parser.add_argument("--queue-worker", required=True)
    parser.add_argument("--n-relaunch", type=int, default=1)
    parser.add_argument("--max-steps", type=int)
    args = parser.parse_args(argv)
    study = WebArenaProStudy.load(args.source_study)
    _fresh_experiments(study, args.max_steps)
    study.dir = args.study_dir
    study.run_queue(args.task_queue, args.queue_worker, n_relaunch=args.n_relaunch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
