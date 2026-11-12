#!/usr/bin/env python
from __future__ import annotations

import argparse
import logging
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT.parent / ".env")
load_dotenv(REPO_ROOT / ".env", override=False)

from agentlab.experiments.loop import yield_all_exp_results

from webarena_pro_bgym.study import WebArenaProStudy


LOGGER = logging.getLogger("relaunch_errored_experiments")


@dataclass(frozen=True)
class ErrorCandidate:
    worker_dir: Path
    task_name: str
    task_id: str
    status: str
    sites: tuple[str, ...]
    exp_args: Any | None = None


def task_sites(exp_args: Any) -> tuple[str, ...]:
    task_config = getattr(getattr(exp_args, "env_args", None), "task_config", None)
    sites = getattr(task_config, "sites", None)
    if sites:
        return tuple(str(site) for site in sites)
    website = getattr(task_config, "website", None)
    if website:
        return (str(website),)
    return ()


def task_id_from_name(task_name: str) -> str:
    return task_name.rsplit(".", 1)[-1]


def task_id_from_exp_dir_name(exp_dir_name: str) -> str:
    match = re.search(r"\.([^./_]+)_\d+$", exp_dir_name)
    if match:
        return match.group(1)
    return exp_dir_name


def worker_dirs_for(study_dir: Path) -> list[Path]:
    workers_dir = study_dir / "workers"
    if not workers_dir.exists():
        return [study_dir]
    return sorted(path for path in workers_dir.glob("worker-*") if path.is_dir())


def matching_exp_dirs(worker_dir: Path, task_id: str) -> list[Path]:
    matches: list[Path] = []
    for exp_args_path in worker_dir.glob("**/exp_args.pkl"):
        exp_dir = exp_args_path.parent
        if task_id_from_exp_dir_name(exp_dir.name) == task_id:
            matches.append(exp_dir)
    return sorted(matches)


def reset_task_runtime_artifacts(worker_dir: Path, task_id: str) -> list[Path]:
    removed: list[Path] = []
    for exp_dir in matching_exp_dirs(worker_dir, task_id):
        shutil.rmtree(exp_dir)
        removed.append(exp_dir)
    return removed


def reset_candidates_runtime_artifacts(candidates: list[ErrorCandidate]) -> int:
    removed_count = 0
    for candidate in candidates:
        removed = reset_task_runtime_artifacts(candidate.worker_dir, candidate.task_id)
        removed_count += len(removed)
    return removed_count


def latest_results_by_task_name(worker_dir: Path) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for exp_result in yield_all_exp_results(worker_dir, progress_fn=None):
        task_name = getattr(getattr(exp_result.exp_args, "env_args", None), "task_name", None)
        if not task_name:
            continue
        current = latest.get(task_name)
        if current is None:
            latest[task_name] = exp_result
            continue
        if exp_result.exp_dir.stat().st_mtime >= current.exp_dir.stat().st_mtime:
            latest[task_name] = exp_result
    return latest


def error_candidates(study_dir: Path, include_incomplete: bool = True) -> list[ErrorCandidate]:
    candidates: list[ErrorCandidate] = []
    for worker_dir in worker_dirs_for(study_dir):
        study = WebArenaProStudy.load(worker_dir)
        latest_results = latest_results_by_task_name(worker_dir)
        seen: set[str] = set()
        for exp_args in study.exp_args_list:
            if getattr(exp_args, "is_dummy", False):
                continue
            env_args = getattr(exp_args, "env_args", None)
            task_name = getattr(env_args, "task_name", "")
            if not task_name or task_name in seen:
                continue
            seen.add(task_name)
            current_result = latest_results.get(task_name)
            status = current_result.status if current_result is not None else "incomplete"
            eligible_statuses = {"error", "incomplete"} if include_incomplete else {"error"}
            if status not in eligible_statuses:
                continue
            candidates.append(
                ErrorCandidate(
                    worker_dir=worker_dir,
                    task_name=task_name,
                    task_id=task_id_from_name(task_name),
                    status=status,
                    sites=task_sites(exp_args),
                    exp_args=exp_args,
                )
            )
    return sorted(candidates, key=lambda item: (item.worker_dir.name, item.task_id))


def reset_exp_args_state(exp_args: Any) -> Any:
    if hasattr(exp_args, "is_dummy"):
        exp_args.is_dummy = False
    if hasattr(exp_args, "status"):
        exp_args.status = "incomplete"
    if hasattr(exp_args, "err_msg"):
        exp_args.err_msg = None
    if hasattr(exp_args, "stack_trace"):
        exp_args.stack_trace = None
    if hasattr(exp_args, "worker_fatal_error"):
        exp_args.worker_fatal_error = None
    return exp_args


def relaunch_candidates(
    candidates: list[ErrorCandidate],
    *,
    jobs: int,
    avg_step_timeout: int | None,
) -> None:
    grouped: dict[Path, list[ErrorCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.exp_args is None:
            raise RuntimeError(f"Missing exp_args snapshot for {candidate.task_name}")
        grouped[candidate.worker_dir].append(candidate)

    for worker_dir, group in sorted(grouped.items(), key=lambda item: str(item[0])):
        study = WebArenaProStudy.load(worker_dir)
        if avg_step_timeout is not None:
            study.avg_step_timeout = avg_step_timeout
        study.exp_args_list = [reset_exp_args_state(candidate.exp_args) for candidate in group]
        LOGGER.info(
            "Relaunching %d experiment(s) from %s sequentially inside the worker dir",
            len(study.exp_args_list),
            worker_dir,
        )
        study._run(
            n_jobs=1,
            parallel_backend="sequential",
            strict_reproducibility=False,
        )
        study.get_results(suffix="relaunch")


def aggregate(study_dir: Path) -> None:
    for worker_dir in worker_dirs_for(study_dir):
        try:
            WebArenaProStudy.load(worker_dir).get_results(suffix="relaunch")
        except Exception:
            LOGGER.exception("Failed to aggregate results for %s", worker_dir)


def coordinator(args: argparse.Namespace) -> int:
    study_dir = Path(args.study_dir).expanduser().resolve()

    pending = error_candidates(study_dir, include_incomplete=not args.errors_only)
    if args.limit is not None:
        pending = pending[: args.limit]
    removed_artifacts = reset_candidates_runtime_artifacts(pending)
    LOGGER.info("Found %d experiment(s) to relaunch in %s", len(pending), study_dir)
    LOGGER.info("Removed %d stale experiment directorie(s) before relaunch", removed_artifacts)
    if not pending:
        aggregate(study_dir)
        return 0

    relaunch_candidates(
        pending,
        jobs=args.jobs,
        avg_step_timeout=args.avg_step_timeout,
    )
    aggregate(study_dir)
    remaining = error_candidates(study_dir, include_incomplete=not args.errors_only)
    LOGGER.info("Remaining relaunch candidates after relaunch: %d", len(remaining))
    return 1 if remaining else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Relaunch errored WebArena-Pro experiments."
    )
    parser.add_argument("--study-dir", type=Path, required=True, help="Study directory.")
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Compatibility option; relaunch currently runs sequentially per worker dir.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional cap for smoke tests.")
    parser.add_argument("--avg-step-timeout", type=int, default=None)
    parser.add_argument(
        "--errors-only",
        action="store_true",
        help="Relaunch tasks whose latest result is error; leave incomplete tasks untouched.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
    args = parse_args(argv)
    if args.jobs < 1:
        raise SystemExit("--jobs must be >= 1")
    return coordinator(args)


if __name__ == "__main__":
    raise SystemExit(main())
