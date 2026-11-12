"""Run tasks with tiered/DAG evaluations in the selected split."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from webarena_pro_core.task import CONFIG_DIR
from webarena_pro_core.splits import load_split_tasks, task_ids_for_split

from webarena_pro_bgym.benchmark.benchmark import WebArenaProBenchmark
from webarena_pro_bgym.run_eval_cli import (
    WEBARENA_PRO_CHAT_MODEL_ARGS_DICT,
    _build_agent,
    _make_parallel_study,
    _required_api_key_env_var,
    _resume_existing_study,
    aggregate_parallel_results,
    dry_run_eval,
    ensure_docker_running,
    ensure_sites_ready,
    print_eval_results,
    selected_sites_for_env_args,
)
from webarena_pro_bgym.queue_runner import run_queue_workers
from webarena_pro_bgym.study import WebArenaProStudy

logger = logging.getLogger(__name__)
DEFAULT_AGENT_MODEL = "gemini/gemini-3.5-flash"


def tiered_task_ids_by_site(
    config_dir: Path | str = CONFIG_DIR, *, split: str | None = None,
) -> dict[str, list[str]]:
    """Return task IDs with DAG evaluations, grouped by primary website.

    The shared loader reads embedded evaluations and supports legacy external
    sidecars, so listing and execution use the same task records.
    """
    task_ids_by_site: dict[str, list[str]] = {}
    for task in load_split_tasks(split or "test", config_dir):
        evaluation = task.get("eval", task.get("evaluation"))
        if not isinstance(evaluation, dict) or not isinstance(evaluation.get("nodes"), list):
            continue
        site = task["sites"][0] if task.get("sites") else task["website"]
        task_ids_by_site.setdefault(site, []).append(str(task["task_id"]))
    return task_ids_by_site


def _build_tiered_benchmark(
    *,
    task_ids_by_site: dict[str, list[str]],
    selected_sites: list[str],
    max_steps: int,
    split: str | None = None,
    config_dir: Path | None = None,
) -> tuple[WebArenaProBenchmark, list[Any]]:
    benchmark = WebArenaProBenchmark(sites=selected_sites, split=split, config_dir=config_dir)
    selected_pairs = {
        (site, task_id)
        for site in selected_sites
        for task_id in task_ids_by_site.get(site, [])
    }

    filtered = []
    for env_args in benchmark.env_args_list:
        task_config = env_args.task_config
        pair = (task_config.website, str(task_config.task_id))
        if pair not in selected_pairs:
            continue
        evaluation = task_config.evaluation
        if not isinstance(evaluation, dict) or not isinstance(evaluation.get("nodes"), list):
            raise ValueError(f"Task {task_config.task_id} has no tiered evaluation")
        env_args.max_steps = max_steps
        filtered.append(env_args)

    benchmark.env_args_list = filtered
    benchmark.task_dependencies = {
        f"{benchmark.name}.{env_args.task_config.task_id}": []
        for env_args in filtered
    }
    return benchmark, filtered


def _parse_max_steps(value: str) -> int:
    """Keep unlimited (-1) distinct from an omitted CLI override (None) on resume."""
    if value.lower() == "unlimited":
        return -1
    try:
        steps = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a positive integer, -1, or 'unlimited'") from None
    if steps <= 0 and steps != -1:
        raise argparse.ArgumentTypeError("max steps must be positive; use -1 or 'unlimited' for no limit")
    return steps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run WebArena-Pro tasks with tiered DAG evaluations.",
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--site",
        action="append",
        default=None,
        help="Tiered site to run. Repeat to run multiple sites. Default: all tiered sites.",
    )
    scope.add_argument("--all", action="store_true", help="Run all tiered sites (default).")
    scope.add_argument("--resume-study", help="Resume an existing tiered study.")
    parser.add_argument("--incomplete-only", action="store_true",
                        help="When resuming a queue, run only unstarted tasks; skip failed/interrupted tasks.")
    parser.add_argument("--retry-from-start", action="store_true",
                        help="When resuming, restart failed/interrupted tasks and pay for new agent calls.")
    parser.add_argument(
        "--max-worker-restarts", type=int, default=None,
        help="Consecutive worker replacements without task progress, per slot (0 disables). Default: 3; preserve when resuming.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print discovered tiered task ids and exit.",
    )
    parser.add_argument("--split", choices=("dev", "test"),
                        help="Select Dev or Test before site/task filters (default: Test).")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=CONFIG_DIR,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--max-steps",
        type=_parse_max_steps,
        default=None,
        help=(
            "Max steps per task. Default: 50 for new runs; preserve when resuming. "
            "Leaderboard budgets: 50, 100, unlimited. Use -1 (or 'unlimited') "
            "for no environment step limit; DAG checkpoints run at 50 and 100."
        ),
    )
    parser.add_argument("--n-jobs", "--parallel", type=int, default=1, help="Supervised worker processes.")
    parser.add_argument(
        "--n-relaunch",
        type=int,
        default=1,
        help="Total local attempts per task, including the first (default: 1, no extra retry).",
    )
    parser.add_argument(
        "--agent-model",
        choices=sorted(WEBARENA_PRO_CHAT_MODEL_ARGS_DICT),
        default=DEFAULT_AGENT_MODEL,
        help="Agent model to run for the evaluation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run live DAG checks without an agent episode; may start sites and call judges. Credentials are still checked.",
    )
    reset_group = parser.add_mutually_exclusive_group()
    reset_group.add_argument(
        "--reset-per-task",
        action="store_true",
        help="Compatibility flag. Per-task reset is already the default.",
    )
    reset_group.add_argument(
        "--no-reset-per-task",
        action="store_true",
        help="Reuse existing site containers across tasks.",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip preflight reachability/startup checks; task setup and resets still run.",
    )
    parser.add_argument(
        "--no-autostart",
        action="store_true",
        help="During preflight, fail if a site is unreachable instead of starting it; does not disable worker-container resets.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging for eval backend calls.",
    )
    parser.add_argument(
        "--study-dir",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Comma-separated task IDs, intersected with the selected split and sites.",
    )
    parser.add_argument("--task-queue", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--queue-worker", help=argparse.SUPPRESS)
    return parser


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.explicit_options = {arg.split("=", 1)[0] for arg in (argv or []) if arg.startswith("--")}
    if bool(args.task_queue) != bool(args.queue_worker):
        parser.error("--task-queue and --queue-worker must be supplied together")
    if args.task_queue and (args.n_jobs != 1 or args.resume_study or args.dry_run):
        parser.error("queue workers require --n-jobs 1 and a new agent run")
    if args.n_relaunch < 1:
        parser.error("--n-relaunch must be positive")
    if args.n_jobs < 1:
        parser.error("--n-jobs must be positive")
    if args.max_worker_restarts is not None and args.max_worker_restarts < 0:
        parser.error("--max-worker-restarts must be nonnegative")
    if (args.retry_from_start or args.incomplete_only) and not args.resume_study:
        parser.error("--retry-from-start and --incomplete-only require --resume-study")
    if args.no_reset_per_task and (args.n_jobs != 1 or args.task_queue
                                   or args.max_worker_restarts is not None):
        parser.error("--no-reset-per-task requires one in-process worker and cannot use worker replacement")
    if args.resume_study:
        if args.split or args.task or args.list or args.dry_run:
            parser.error("--resume-study cannot be combined with --split, --task, --list, or --dry-run")
    return args


def _selected_tiered_sites(
    task_ids_by_site: dict[str, list[str]],
    requested_sites: list[str] | None,
) -> list[str]:
    if not requested_sites:
        return sorted(task_ids_by_site)

    known_sites = set(task_ids_by_site)
    selected = list(dict.fromkeys(requested_sites))
    unknown = sorted(set(selected) - known_sites)
    if unknown:
        raise SystemExit(
            "No tiered tasks found for site(s) "
            f"{', '.join(unknown)}. Known tiered sites: {', '.join(sorted(known_sites))}"
        )
    return selected


def _print_tiered_tasks(task_ids_by_site: dict[str, list[str]], sites: list[str]) -> None:
    total = 0
    for site in sites:
        task_ids = task_ids_by_site[site]
        total += len(task_ids)
        print(f"{site}: {','.join(task_ids)}")
    print(f"total: {total}")


def _parse_task_filter(raw_task_ids: str | None) -> set[str] | None:
    if raw_task_ids is None:
        return None
    return {
        token.strip().zfill(3)
        for token in raw_task_ids.split(",")
        if token.strip()
    }


def _filter_task_ids_by_site(
    task_ids_by_site: dict[str, list[str]],
    selected_task_ids: set[str] | None,
) -> dict[str, list[str]]:
    if selected_task_ids is None:
        return task_ids_by_site
    return {
        site: [task_id for task_id in task_ids if task_id in selected_task_ids]
        for site, task_ids in task_ids_by_site.items()
    }


def _task_sites_by_id(filtered: list[Any]) -> dict[int, list[str]]:
    task_sites_by_id: dict[int, list[str]] = {}
    for env_args in filtered:
        task_config = env_args.task_config
        task_sites = getattr(task_config, "sites", None)
        if task_sites:
            sites = [str(site) for site in task_sites]
        else:
            sites = [str(task_config.website)]
        task_sites_by_id[int(task_config.task_id)] = sites
    return task_sites_by_id


def run_tiered_parallel(
    *,
    args: argparse.Namespace,
    benchmark: WebArenaProBenchmark,
    filtered: list[Any],
    task_ids_by_site: dict[str, list[str]],
    selected_sites: list[str],
) -> int:
    """Spawn isolated worker subprocesses for the tiered/DAG task set."""
    if args.dry_run:
        logger.error("--n-jobs is only supported for full agent runs, not --dry-run.")
        return 2

    if not ensure_docker_running():
        return 1

    task_sites = dict(sorted(_task_sites_by_id(filtered).items()))
    if not task_sites:
        logger.error("No tiered tasks matched the selected site(s): %s", selected_sites)
        return 1
    try:
        parent_study = _make_parallel_study(
            benchmark=benchmark,
            comment="tiered-eval",
            suffix="tiered-parallel",
            agent_model=args.agent_model,
            study_dir=args.study_dir,
        )
    except ValueError as error:
        logger.error("%s", error)
        return 1
    command = [
        sys.executable, str(Path(__file__).resolve()),
        "--task", ",".join(str(task_id) for task_id in task_sites),
        "--reset-per-task", "--max-steps", str(args.max_steps),
        "--skip-preflight", "--n-jobs", "1",
        "--n-relaunch", str(args.n_relaunch),
        "--agent-model", args.agent_model,
        "--config-dir", str(args.config_dir.resolve()),
    ]
    for site in selected_sites:
        command.extend(["--site", site])
    if args.split:
        command.extend(["--split", args.split])
    if args.verbose:
        command.append("--verbose")
    run_start_time = time.time()
    logger.info("Tiered FIFO queue: %d workers, %d tasks, parent study=%s",
                min(args.n_jobs, len(task_sites)), len(task_sites), parent_study.dir)
    try:
        result = run_queue_workers(
            task_sites=task_sites, worker_count=args.n_jobs,
            root_dir=parent_study.dir, command=command,
            max_worker_restarts=args.max_worker_restarts if args.max_worker_restarts is not None else 3,
        )
    except (OSError, ValueError) as error:
        logger.error("Could not run queued study: %s", error)
        return 1
    except KeyboardInterrupt:
        logger.warning("Queued study interrupted; use --resume-study %s to continue from checkpoints", parent_study.dir)
        return 130
    aggregate_parallel_results(site="tiered", root_dir=parent_study.dir, since=run_start_time)
    if any(parent_study.dir.glob("**/summary_info.json")):
        parent_study.get_results(suffix="parallel")
    logger.info("Tiered parallel parent study saved to %s", parent_study.dir)
    return result


def _resume_parallel_queue(args: argparse.Namespace) -> int:
    from webarena_pro_bgym.task_queue import TaskQueue

    root_dir = Path(args.resume_study).expanduser().resolve()
    if args.no_reset_per_task:
        logger.error("Queued resume requires per-task reset to replay saved actions safely")
        return 2
    try:
        settings = json.loads((root_dir / "queue_run.json").read_text())
        saved_command = settings["command"]
        if (not isinstance(saved_command, list) or len(saved_command) < 2
                or not all(isinstance(arg, str) for arg in saved_command)):
            raise ValueError("Invalid saved worker command")
        if settings.get("prewarm") is not None and type(settings["prewarm"]) is not bool:
            raise ValueError("Invalid saved prewarm setting")
        # Use today's entry point/runtime with the original resolved task
        # filters, config directory, model and per-task limits.
        is_legacy = "--source-study" in saved_command[2:]
        entrypoint = Path(__file__).with_name("legacy_recovery.py") if is_legacy else Path(__file__)
        command = [sys.executable, str(entrypoint.resolve()), *saved_command[2:]]
        for option, value in (("--max-steps", args.max_steps),
                              ("--n-relaunch", args.n_relaunch if "--n-relaunch" in args.explicit_options else None)):
            if value is not None:
                if option in command:
                    index = command.index(option)
                    command[index + 1] = str(value)
                else:
                    command.extend([option, str(value)])
        worker_count = (args.n_jobs if {"--n-jobs", "--parallel"} & args.explicit_options
                        else int(settings["worker_count"]))
        max_worker_restarts = (args.max_worker_restarts if args.max_worker_restarts is not None
                               else settings.get("max_worker_restarts", 3))
        if type(max_worker_restarts) is not int or max_worker_restarts < 0:
            raise ValueError("Invalid saved worker restart limit")
        resume_mode = "incomplete" if args.incomplete_only else "fresh" if args.retry_from_start else "continue"
        records = TaskQueue.load(root_dir / "queue.jsonl").status()
        task_sites = {row["task_id"]: row["sites"] for row in records}
        runnable_states = {"pending", "claimed"}
        if resume_mode != "incomplete":
            runnable_states.update({"failed", "interrupted", "started"})
        if any(row["state"] in runnable_states for row in records):
            # Migrated studies retain serialized agent arguments, which need
            # not correspond to one of today's named model presets.
            original = None if is_legacy else _parse_args(command[2:])
            required_env = _required_api_key_env_var(original.agent_model) if original else None
            if required_env and not os.environ.get(required_env):
                logger.error("%s not set; required by the saved agent model", required_env)
                return 1
            if not ensure_docker_running():
                return 1
        result = run_queue_workers(
            task_sites=task_sites, worker_count=worker_count, root_dir=root_dir,
            command=command, resume=True, prewarm=settings.get("prewarm"),
            resume_mode=resume_mode, max_worker_restarts=max_worker_restarts,
        )
        aggregate_parallel_results(site="tiered", root_dir=root_dir)
        if any(root_dir.glob("**/summary_info.json")):
            WebArenaProStudy.load(root_dir).get_results(suffix="parallel")
        return result
    except (OSError, ValueError, KeyError, TypeError) as error:
        logger.error("Cannot resume queued study %s: %s", root_dir, error)
        return 1
    except KeyboardInterrupt:
        logger.warning("Queued study interrupted; resume again with --resume-study %s", root_dir)
        return 130


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))

    if args.verbose:
        logging.getLogger("webarena_pro_core.eval").setLevel(logging.DEBUG)

    if args.no_reset_per_task:
        os.environ["WP_RESET_CONTAINER_PER_TASK"] = "0"
    else:
        os.environ["WP_RESET_CONTAINER_PER_TASK"] = "1"

    if args.resume_study:
        source = Path(args.resume_study).expanduser()
        if (source / "_recovery" / "queue.jsonl").exists():
            args.resume_study = str(source / "_recovery")
        if (Path(args.resume_study).expanduser() / "queue.jsonl").exists():
            return _resume_parallel_queue(args)
        return _resume_existing_study(args)

    if args.study_dir:
        destination = Path(args.study_dir).expanduser()
        if any((destination / name).exists() for name in ("study.pkl.gz", "queue.jsonl", "task_queue.sqlite3")):
            logger.error("Study directory already contains a run: %s. Use --resume-study %s", destination, destination)
            return 1

    task_ids_by_site = tiered_task_ids_by_site(args.config_dir, split=args.split)
    sites = _selected_tiered_sites(task_ids_by_site, args.site)
    task_filter = _parse_task_filter(args.task)
    if args.split:
        split_ids = task_ids_for_split(args.split, args.config_dir)
        task_filter = split_ids if task_filter is None else task_filter & split_ids
    task_ids_by_site = _filter_task_ids_by_site(task_ids_by_site, task_filter)
    sites = [site for site in sites if task_ids_by_site.get(site)]
    if not sites:
        logger.error("No tiered tasks match the selected split/site/task filters")
        return 1

    if args.list:
        _print_tiered_tasks(task_ids_by_site, sites)
        return 0

    required_env = _required_api_key_env_var(args.agent_model)
    if required_env and not os.environ.get(required_env):
        logger.error("%s not set. Add it to .env or export it.", required_env)
        return 1

    max_steps = int(args.max_steps if args.max_steps is not None else 50)
    args.max_steps = max_steps
    if args.dry_run:
        if not ensure_sites_ready(sites, args):
            return 1
        for site in sites:
            dry_run_eval(site, [int(task_id) for task_id in task_ids_by_site[site]],
                         split=args.split, config_dir=args.config_dir)
        return 0

    benchmark, filtered = _build_tiered_benchmark(
        task_ids_by_site=task_ids_by_site,
        selected_sites=sites,
        max_steps=max_steps,
        split=args.split,
        config_dir=args.config_dir,
    )
    if not filtered:
        logger.error("No tiered tasks matched the selected site(s): %s", sites)
        return 1

    if not args.task_queue and not args.no_reset_per_task:
        return run_tiered_parallel(
            args=args,
            benchmark=benchmark,
            filtered=filtered,
            task_ids_by_site=task_ids_by_site,
            selected_sites=sites,
        )

    selected_runtime_sites = selected_sites_for_env_args(filtered)
    if not ensure_sites_ready(selected_runtime_sites, args):
        return 1

    logger.info(
        "Running %d tiered task(s): %s",
        len(filtered),
        {
            site: task_ids_by_site[site]
            for site in sites
        },
    )

    study = WebArenaProStudy(
        agent_args=[_build_agent(args.agent_model)],
        benchmark=benchmark,
        comment="tiered-eval",
        suffix="tiered-eval",
        dir=Path(args.study_dir) if args.study_dir else None,
    )
    if args.task_queue:
        study.run_queue(args.task_queue, args.queue_worker, n_relaunch=args.n_relaunch)
    else:
        study.run(
            n_jobs=1,
            parallel_backend="sequential",
            n_relaunch=args.n_relaunch,
        )
    print_eval_results(study.dir, "tiered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
