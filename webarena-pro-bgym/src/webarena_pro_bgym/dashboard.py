from __future__ import annotations

import gzip
import json
import os
import pickle
import re
import shlex
import signal
import subprocess
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from webarena_pro_bgym.utils import has_ungraded_score

RESOURCE_SCHEDULER_STATUS_FILE = "resource_scheduler_status.json"
RESOURCE_SCHEDULER_EVENTS_DIR = "resource_scheduler_events"

STOP_STUDY_GRACE_SECONDS = 3.0
STOP_STUDY_POLL_INTERVAL_SECONDS = 0.2
RECENT_INCOMPLETE_RUN_SECONDS = 15 * 60


def default_results_root() -> Path:
    return Path(os.environ.get("AGENTLAB_RESULTS_DIR", Path.home() / "agentlab_results")).expanduser()


def isoformat_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_task_id_from_exp_dir(exp_dir_name: str) -> str:
    match = re.search(r"\.([^./_]+)_\d+$", exp_dir_name)
    if match:
        return match.group(1)
    return exp_dir_name


def _load_pickle(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rb") as handle:
            return pickle.load(handle)
    except Exception:
        return None


def _task_entries_from_study_pickle(study_pickle: Path) -> list[dict[str, Any]]:
    study = _load_pickle(study_pickle)
    if study is None:
        return []

    entries: list[dict[str, Any]] = []
    exp_args_list = getattr(study, "exp_args_list", None) or []
    for index, exp_args in enumerate(exp_args_list):
        env_args = getattr(exp_args, "env_args", None)
        task_config = getattr(env_args, "task_config", None)
        task_id = getattr(task_config, "task_id", None)
        task_name = getattr(env_args, "task_name", None)
        if task_id is None:
            continue
        entries.append(
            {
                "task_id": str(task_id),
                "task_name": task_name,
                "order": index,
                "sites": _task_sites_from_config(task_config),
            }
        )
    return entries


def _task_sites_from_config(task_config: Any) -> list[str]:
    if task_config is None:
        return []
    sites = getattr(task_config, "sites", None)
    if sites:
        return [str(site) for site in sites]
    website = getattr(task_config, "website", None)
    return [str(website)] if website else []


def _study_name_from_pickle(study_pickle: Path, fallback: str) -> str:
    study = _load_pickle(study_pickle)
    if study is None:
        return fallback
    return str(getattr(study, "name", fallback))


def list_top_level_studies(results_root: Path | None = None, limit: int = 20) -> list[Path]:
    root = (results_root or default_results_root()).expanduser()
    if not root.exists():
        return []

    studies = [
        directory
        for directory in root.iterdir()
        if directory.is_dir() and (directory / "study.pkl.gz").exists()
    ]
    studies.sort(key=lambda directory: (directory.stat().st_mtime, directory.name), reverse=True)
    return studies[:limit]


@dataclass
class StudyTaskRecord:
    task_id: str
    task_name: str | None
    order: int
    worker: str
    status: str
    started_at: str | None
    reward: float | None
    n_steps: int | None
    observed_steps: int
    updated_at: str | None
    elapsed_seconds: float | None
    err_msg: str | None
    exp_relative_dir: str | None
    artifacts: dict[str, str]
    sites: list[str]


def _iter_experiment_dirs(study_dir: Path) -> list[Path]:
    exp_dirs = []
    for exp_args_path in study_dir.glob("**/exp_args.pkl"):
        exp_dir = exp_args_path.parent
        if exp_dir == study_dir:
            continue
        exp_dirs.append(exp_dir)
    return sorted(exp_dirs)


def _preferred_exp_dir(current: Path | None, candidate: Path) -> Path:
    if current is None:
        return candidate

    current_archived = current.name.startswith("_")
    candidate_archived = candidate.name.startswith("_")
    if current_archived != candidate_archived:
        return current if not current_archived else candidate

    current_mtime = current.stat().st_mtime if current.exists() else float("-inf")
    candidate_mtime = candidate.stat().st_mtime if candidate.exists() else float("-inf")
    if candidate_mtime != current_mtime:
        return candidate if candidate_mtime > current_mtime else current

    return candidate if candidate.name > current.name else current


def _worker_name_for_exp_dir(study_dir: Path, exp_dir: Path) -> str:
    relative_parts = exp_dir.relative_to(study_dir).parts
    if len(relative_parts) >= 2 and relative_parts[0] == "workers":
        return relative_parts[1]
    return "main"


def _planned_worker_map(study_dir: Path) -> dict[str, str]:
    workers_dir = study_dir / "workers"
    if not workers_dir.exists():
        return {}

    mapping: dict[str, str] = {}
    for worker_dir in sorted(child for child in workers_dir.iterdir() if child.is_dir()):
        for task in _task_entries_from_study_pickle(worker_dir / "study.pkl.gz"):
            mapping[task["task_id"]] = worker_dir.name
    return mapping


def _task_status_from_summary(summary: dict[str, Any]) -> str:
    if summary.get("err_msg"):
        return "error"
    if has_ungraded_score(summary):
        return "failed"
    reward = _safe_float(summary.get("cum_reward"))
    if reward is None:
        return "error"
    if reward >= 1.0:
        return "passed"
    if reward > 0:
        return "partial"
    return "failed"


def _latest_mtime(paths: list[Path]) -> float | None:
    mtimes = []
    for path in paths:
        if path.exists():
            mtimes.append(path.stat().st_mtime)
    return max(mtimes) if mtimes else None


def _earliest_mtime(paths: list[Path]) -> float | None:
    mtimes = []
    for path in paths:
        if path.exists():
            mtimes.append(path.stat().st_mtime)
    return min(mtimes) if mtimes else None


def _elapsed_seconds(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return max(0.0, round(end - start, 3))


def _parse_ps_output(output: str) -> list[dict[str, Any]]:
    processes: list[dict[str, Any]] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 2)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        ppid = None
        command_index = 1
        if len(parts) > 1:
            try:
                ppid = int(parts[1])
                command_index = 2
            except ValueError:
                ppid = None
        command = " ".join(parts[command_index:]) if len(parts) > command_index else ""
        processes.append({"pid": pid, "ppid": ppid, "command": command})
    return processes


def _study_command_matches(study_dir: Path, command: str) -> bool:
    command_lower = command.lower()
    if str(study_dir) not in command:
        return False
    if command_lower.startswith("tmux ") or "tmux new-session" in command_lower:
        return False
    if (
        "run_dashboard_cli" in command_lower
        or "webarena_pro_bgym.dashboard" in command_lower
    ):
        return False
    args = _parse_command_args(command)
    for index, token in enumerate(args):
        if (
            Path(token).name in {"webarena-pro", "webarena_pro_core.cli"}
            and args[index + 1:index + 3] == ["run", "dashboard"]
        ) or (
            token == "webarena_pro_bgym.run_cli"
            and args[index + 1:index + 2] == ["dashboard"]
        ):
            return False
    return (
        "webarena_pro_bgym.run_eval_cli" in command_lower
        or "run_eval_cli.py" in command_lower
        or "relaunch_errored_experiments.py" in command_lower
        or ("--run-one" in command_lower and "--worker-dir" in command_lower)
        or "--study-dir" in command_lower
        or "--resume-study" in command_lower
    )


def _parse_command_args(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _command_flag_value(command: str, flag: str) -> str | None:
    args = _parse_command_args(command)
    for index, token in enumerate(args):
        if token == flag and index + 1 < len(args):
            return args[index + 1]
        if token.startswith(flag + "="):
            return token.split("=", 1)[1]
    return None


def _command_references_path(command: str, path: Path) -> bool:
    path_value = str(path)
    args = _parse_command_args(command)
    for token in args:
        if token == path_value or token.endswith("=" + path_value):
            return True

    start = 0
    while True:
        index = command.find(path_value, start)
        if index < 0:
            return False
        before = command[index - 1] if index > 0 else ""
        after_index = index + len(path_value)
        after = command[after_index] if after_index < len(command) else ""
        before_ok = not before or before.isspace() or before in "='\""
        after_ok = not after or after.isspace() or after in "'\""
        if before_ok and after_ok:
            return True
        start = index + 1


def _task_id_from_task_name(task_name: str | None) -> str | None:
    if not task_name:
        return None
    return task_name.rsplit(".", 1)[-1]


def _task_id_from_exp_args_path(exp_args_path: Path) -> str | None:
    match = re.search(r"-([^-/]+)\.pkl$", exp_args_path.name)
    if match:
        return match.group(1)

    try:
        with exp_args_path.open("rb") as handle:
            exp_args = pickle.load(handle)
    except Exception:
        return None

    env_args = getattr(exp_args, "env_args", None)
    task_config = getattr(env_args, "task_config", None)
    task_id = getattr(task_config, "task_id", None)
    return None if task_id is None else str(task_id)


def find_study_processes(study_dir: Path, ps_output: str | None = None) -> list[dict[str, Any]]:
    resolved_study_dir = study_dir.expanduser().resolve()
    if ps_output is None:
        result = subprocess.run(
            ["ps", "-ax", "-o", "pid=", "-o", "ppid=", "-o", "command="],
            capture_output=True,
            text=True,
            check=True,
        )
        ps_output = result.stdout

    parsed_processes = _parse_ps_output(ps_output)
    children_by_parent: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for process in parsed_processes:
        ppid = process.get("ppid")
        if ppid is not None:
            children_by_parent[int(ppid)].append(process)

    matched_pids: set[int] = set()
    processes = []
    for process in parsed_processes:
        pid = int(process["pid"])
        command = str(process.get("command", ""))
        if _study_command_matches(resolved_study_dir, command):
            matched_pids.add(pid)
            process_copy = dict(process)
            processes.append(process_copy)

    queue = list(matched_pids)
    seen_descendants = set(matched_pids)
    while queue:
        current_pid = queue.pop(0)
        for child in children_by_parent.get(current_pid, []):
            child_pid = int(child["pid"])
            if child_pid in seen_descendants:
                continue
            seen_descendants.add(child_pid)
            queue.append(child_pid)
            child_copy = dict(child)
            processes.append(child_copy)

    return processes


def _live_workers_for_study(study_dir: Path, running_processes: list[dict[str, Any]]) -> set[str]:
    workers: set[str] = set()
    workers_root = study_dir / "workers"

    for process in running_processes:
        command = str(process.get("command", ""))
        matched_worker = None
        if workers_root.exists():
            for worker_dir in workers_root.iterdir():
                if not worker_dir.is_dir():
                    continue
                if _command_references_path(command, worker_dir):
                    matched_worker = worker_dir.name
                    break
        workers.add(matched_worker or "main")

    return workers


def _active_relaunch_tasks_for_study(
    study_dir: Path, running_processes: list[dict[str, Any]]
) -> dict[str, dict[str, str]]:
    resolved_study_dir = study_dir.expanduser().resolve()
    active_tasks: dict[str, dict[str, str]] = {}

    for process in running_processes:
        command = str(process.get("command", ""))
        if "--run-one" not in command:
            continue

        worker_dir_value = _command_flag_value(command, "--worker-dir")
        task_name = _command_flag_value(command, "--task-name")
        task_id = _task_id_from_task_name(task_name)
        if task_id is None:
            exp_args_path_value = _command_flag_value(command, "--exp-args-path")
            if exp_args_path_value is not None:
                task_id = _task_id_from_exp_args_path(
                    Path(exp_args_path_value).expanduser()
                )
        if worker_dir_value is None or task_id is None:
            continue

        worker_dir = Path(worker_dir_value).expanduser().resolve()
        if worker_dir == resolved_study_dir:
            worker_name = "main"
        else:
            try:
                relative_parts = worker_dir.relative_to(resolved_study_dir).parts
            except ValueError:
                continue
            if len(relative_parts) >= 2 and relative_parts[0] == "workers":
                worker_name = relative_parts[1]
            else:
                worker_name = "main"

        active_tasks[task_id] = {"worker": worker_name}

    return active_tasks


def _normalise_timestamp(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    numeric = _safe_float(value)
    return isoformat_timestamp(numeric)


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalise_lifecycle_status(raw_worker: dict[str, Any]) -> str:
    lifecycle_status = raw_worker.get("lifecycle_status")
    if lifecycle_status is None:
        lifecycle_status = raw_worker.get("status")
    normalized = str(lifecycle_status or "unknown").lower()
    if normalized in {"idle", "busy", "healthy"}:
        return "running"
    if normalized in {"created", "restarting"}:
        return "starting"
    if normalized in {"exited", "dead", "removing"}:
        return "stopped"
    return normalized


def _normalise_allocation_status(raw_worker: dict[str, Any]) -> str:
    allocation_status = raw_worker.get("allocation_status")
    if allocation_status is not None:
        return str(allocation_status).lower()
    if raw_worker.get("in_use") is True or raw_worker.get("task_id") is not None:
        return "in-use"
    return "free"


def _normalise_website_worker_status(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "source": "none",
            "updated_at": None,
            "worker_count": None,
            "sites": [],
        }

    normalised_sites: list[dict[str, Any]] = []
    for raw_site in payload.get("sites") or []:
        if not isinstance(raw_site, dict):
            continue
        site_name = str(raw_site.get("site") or "")
        if not site_name:
            continue

        workers: list[dict[str, Any]] = []
        for raw_worker in raw_site.get("workers") or []:
            if not isinstance(raw_worker, dict):
                continue
            worker_index = _safe_int(raw_worker.get("worker_index"))
            worker_name = raw_worker.get("worker")
            if worker_name is None and worker_index is not None:
                worker_name = f"{site_name}-w{worker_index}"
            lifecycle_status = _normalise_lifecycle_status(raw_worker)
            allocation_status = _normalise_allocation_status(raw_worker)

            workers.append(
                {
                    "site": site_name,
                    "worker_index": worker_index,
                    "worker": str(worker_name or ""),
                    "status": lifecycle_status,
                    "lifecycle_status": lifecycle_status,
                    "allocation_status": allocation_status,
                    "in_use": allocation_status == "in-use",
                    "task_id": raw_worker.get("task_id"),
                    "log_path": raw_worker.get("log_path"),
                    "container_name": raw_worker.get("container_name"),
                    "container_status": raw_worker.get("container_status"),
                    "health": raw_worker.get("health"),
                    "exp_hash": raw_worker.get("exp_hash"),
                    "error": raw_worker.get("error"),
                }
            )

        workers.sort(
            key=lambda worker: (
                worker["worker_index"] is None,
                worker["worker_index"] if worker["worker_index"] is not None else 0,
                worker["worker"],
            )
        )
        lifecycle_counts = Counter(worker["lifecycle_status"] for worker in workers)
        allocation_counts = Counter(worker["allocation_status"] for worker in workers)
        normalised_sites.append(
            {
                "site": site_name,
                "remaining_tasks": raw_site.get("remaining_tasks"),
                "stopped": bool(raw_site.get("stopped", False)),
                "workers": workers,
                "counts": dict(sorted(lifecycle_counts.items())),
                "lifecycle_counts": dict(sorted(lifecycle_counts.items())),
                "allocation_counts": dict(sorted(allocation_counts.items())),
            }
        )

    worker_count = _safe_int(payload.get("worker_count"))
    if worker_count is None and normalised_sites:
        worker_count = max(len(site["workers"]) for site in normalised_sites)

    normalised_sites.sort(key=lambda site: site["site"])
    return {
        "source": str(payload.get("source") or "scheduler"),
        "updated_at": _normalise_timestamp(payload.get("updated_at")),
        "worker_count": worker_count,
        "pending_tasks": payload.get("pending_tasks") or [],
        "running_tasks": payload.get("running_tasks") or [],
        "finished_tasks": payload.get("finished_tasks") or [],
        "sites": normalised_sites,
    }


def _load_scheduler_worker_status(study_dir: Path) -> dict[str, Any] | None:
    status_path = study_dir / RESOURCE_SCHEDULER_STATUS_FILE
    if not status_path.exists():
        return None
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    payload = dict(payload)
    payload["source"] = "scheduler"
    return _normalise_website_worker_status(payload)


def _load_scheduler_worker_events(study_dir: Path) -> dict[tuple[str, int], dict[str, Any]]:
    events_dir = study_dir / RESOURCE_SCHEDULER_EVENTS_DIR
    if not events_dir.exists():
        return {}

    events: dict[tuple[str, int], dict[str, Any]] = {}
    for event_path in events_dir.glob("*.json"):
        try:
            event = json.loads(event_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(event, dict):
            continue
        site = event.get("site")
        worker_index = _safe_int(event.get("worker_index"))
        if site is None or worker_index is None:
            continue
        previous = events.get((str(site), worker_index))
        event_updated_at = _safe_float(event.get("updated_at")) or 0
        previous_updated_at = (
            _safe_float(previous.get("updated_at")) or 0 if previous is not None else -1
        )
        if previous is None or event_updated_at > previous_updated_at:
            events[(str(site), worker_index)] = event
    return events


def _merge_scheduler_worker_events(
    scheduler_status: dict[str, Any],
    events: dict[tuple[str, int], dict[str, Any]],
) -> dict[str, Any]:
    if not events:
        return scheduler_status

    for site in scheduler_status.get("sites", []):
        site_name = site.get("site")
        for worker in site.get("workers", []):
            worker_index = worker.get("worker_index")
            if site_name is None or worker_index is None:
                continue
            if worker.get("allocation_status") != "in-use":
                continue

            event = events.get((str(site_name), int(worker_index)))
            if event is None:
                continue
            if str(event.get("task_id")) != str(worker.get("task_id")):
                continue

            lifecycle_status = _normalise_lifecycle_status(event)
            worker["status"] = lifecycle_status
            worker["lifecycle_status"] = lifecycle_status
            worker["event_updated_at"] = _normalise_timestamp(event.get("updated_at"))

    for site in scheduler_status.get("sites", []):
        workers = site.get("workers", [])
        lifecycle_counts = Counter(worker["lifecycle_status"] for worker in workers)
        allocation_counts = Counter(worker["allocation_status"] for worker in workers)
        site["counts"] = dict(sorted(lifecycle_counts.items()))
        site["lifecycle_counts"] = dict(sorted(lifecycle_counts.items()))
        site["allocation_counts"] = dict(sorted(allocation_counts.items()))
    return scheduler_status


def _container_worker_status(container_status: str | None, health: str | None) -> str:
    status = (container_status or "").lower()
    health_status = (health or "").lower()
    if status == "running":
        if health_status in {"healthy", "unhealthy", "starting"}:
            return health_status
        return "running"
    if status in {"exited", "dead", "removing"}:
        return "stopped"
    if status:
        return status
    return "unknown"


def _discover_docker_website_workers() -> dict[str, Any] | None:
    try:
        import docker
        from webarena_pro_core import LABEL_EXP_HASH, LABEL_MANAGED, LABEL_SITE
    except Exception:
        return None

    try:
        containers = docker.from_env().containers.list(
            all=True,
            filters={"label": f"{LABEL_MANAGED}=website"},
        )
    except Exception:
        return None

    sites: dict[str, dict[str, Any]] = {}
    for container in containers:
        labels = getattr(container, "labels", None) or {}
        name = str(getattr(container, "name", "") or "")
        match = re.fullmatch(r"(.+)-w(\d+)", name)
        exp_hash = labels.get(LABEL_EXP_HASH)
        worker_index = None
        if isinstance(exp_hash, str):
            exp_match = re.fullmatch(r"w(\d+)", exp_hash)
            if exp_match:
                worker_index = int(exp_match.group(1))
        if worker_index is None and match:
            worker_index = int(match.group(2))
        if worker_index is None:
            continue

        site_name = labels.get(LABEL_SITE) or (match.group(1) if match else None)
        if not site_name:
            continue

        attrs = getattr(container, "attrs", None) or {}
        state = attrs.get("State") or {}
        health = (state.get("Health") or {}).get("Status")
        container_status = state.get("Status") or getattr(container, "status", None)
        site_entry = sites.setdefault(
            str(site_name),
            {
                "site": str(site_name),
                "remaining_tasks": None,
                "stopped": False,
                "workers": [],
            },
        )
        site_entry["workers"].append(
            {
                "site": str(site_name),
                "worker_index": worker_index,
                "worker": f"{site_name}-w{worker_index}",
                "status": _container_worker_status(container_status, health),
                "task_id": None,
                "container_name": name,
                "container_status": container_status,
                "health": health,
                "exp_hash": exp_hash,
            }
        )

    if not sites:
        return None

    worker_count = max(len(site["workers"]) for site in sites.values())
    return _normalise_website_worker_status(
        {
            "source": "docker",
            "updated_at": time.time(),
            "worker_count": worker_count,
            "sites": sorted(sites.values(), key=lambda site: site["site"]),
        }
    )


def _merge_docker_worker_health(
    scheduler_status: dict[str, Any],
    docker_status: dict[str, Any] | None,
) -> dict[str, Any]:
    if not docker_status:
        return scheduler_status

    docker_workers: dict[tuple[str, int], dict[str, Any]] = {}
    for site in docker_status.get("sites", []):
        site_name = site.get("site")
        for worker in site.get("workers", []):
            worker_index = worker.get("worker_index")
            if site_name is not None and worker_index is not None:
                docker_workers[(str(site_name), int(worker_index))] = worker

    for site in scheduler_status.get("sites", []):
        site_name = site.get("site")
        for worker in site.get("workers", []):
            worker_index = worker.get("worker_index")
            if site_name is None or worker_index is None:
                continue
            docker_worker = docker_workers.get((str(site_name), int(worker_index)))
            if docker_worker is None:
                continue
            for key in ("container_name", "container_status", "health", "exp_hash"):
                if docker_worker.get(key) is not None:
                    worker[key] = docker_worker[key]
    return scheduler_status


def _worker_index_from_task_worker(worker_name: str) -> int | None:
    match = re.fullmatch(r"worker-(\d+)", str(worker_name))
    if not match:
        return None
    return int(match.group(1))


def _refresh_website_worker_counts(website_worker_status: dict[str, Any]) -> None:
    for site in website_worker_status.get("sites", []):
        workers = site.get("workers") or []
        lifecycle_counts = Counter(worker.get("lifecycle_status") for worker in workers)
        allocation_counts = Counter(worker.get("allocation_status") for worker in workers)
        site["counts"] = dict(sorted(lifecycle_counts.items()))
        site["lifecycle_counts"] = dict(sorted(lifecycle_counts.items()))
        site["allocation_counts"] = dict(sorted(allocation_counts.items()))


def _infer_website_worker_allocations_from_tasks(
    website_worker_status: dict[str, Any],
    task_records: list[StudyTaskRecord],
) -> dict[str, Any]:
    """Mark Docker-discovered website workers in-use when task rows show use.

    Docker can tell us ``mattermost-w1`` exists and is running, but not whether
    ``worker-1`` is currently executing a Mattermost task. Infer that allocation
    from the task table so Docker-only worker panels do not misleadingly show
    running containers as free.
    """
    running_by_site_and_worker: dict[tuple[str, int], StudyTaskRecord] = {}
    running_by_worker_without_sites: dict[int, StudyTaskRecord] = {}
    for record in task_records:
        if record.status != "running":
            continue
        worker_index = _worker_index_from_task_worker(record.worker)
        if worker_index is None:
            continue
        if record.sites:
            for site in record.sites:
                running_by_site_and_worker[(site, worker_index)] = record
        else:
            running_by_worker_without_sites[worker_index] = record

    if not running_by_site_and_worker and not running_by_worker_without_sites:
        return website_worker_status

    changed = False
    for site in website_worker_status.get("sites", []):
        site_name = str(site.get("site") or "")
        if not site_name:
            continue
        for worker in site.get("workers") or []:
            worker_index = _safe_int(worker.get("worker_index"))
            if worker_index is None:
                continue

            record = running_by_site_and_worker.get((site_name, worker_index))
            if record is None:
                record = running_by_worker_without_sites.get(worker_index)
            if record is None:
                continue

            worker["allocation_status"] = "in-use"
            worker["in_use"] = True
            worker["task_id"] = record.task_id
            worker["task_name"] = record.task_name
            changed = True

    if changed:
        _refresh_website_worker_counts(website_worker_status)
    return website_worker_status


def _website_worker_status_for_study(
    study_dir: Path,
    running_processes: list[dict[str, Any]],
) -> dict[str, Any]:
    scheduler_status = _load_scheduler_worker_status(study_dir)
    if scheduler_status is not None:
        scheduler_status = _merge_scheduler_worker_events(
            scheduler_status,
            _load_scheduler_worker_events(study_dir),
        )
        docker_status = _discover_docker_website_workers() if running_processes else None
        return _merge_docker_worker_health(scheduler_status, docker_status)

    docker_status = _discover_docker_website_workers() if running_processes else None
    if docker_status is not None:
        return docker_status

    return _normalise_website_worker_status(None)


def stop_study_processes(study_dir: Path) -> dict[str, Any]:
    resolved_study_dir = study_dir.expanduser().resolve()
    matched = find_study_processes(resolved_study_dir)

    stopped_pids: list[int] = []
    for process in matched:
        pid = int(process["pid"])
        try:
            os.kill(pid, signal.SIGTERM)
            stopped_pids.append(pid)
        except ProcessLookupError:
            continue

    deadline = time.time() + STOP_STUDY_GRACE_SECONDS
    remaining_pids = set(stopped_pids)
    while remaining_pids and time.time() < deadline:
        finished_pids = set()
        for pid in remaining_pids:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                finished_pids.add(pid)
        if finished_pids:
            remaining_pids.difference_update(finished_pids)
            if not remaining_pids:
                break
        time.sleep(STOP_STUDY_POLL_INTERVAL_SECONDS)

    escalated_pids: list[int] = []
    for pid in sorted(remaining_pids):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        os.kill(pid, signal.SIGKILL)
        escalated_pids.append(pid)

    return {
        "study_dir": resolved_study_dir,
        "matched_pids": [int(process["pid"]) for process in matched],
        "stopped_pids": stopped_pids,
        "escalated_pids": escalated_pids,
    }


def build_run_snapshot(study_dir: Path) -> dict[str, Any]:
    study_dir = study_dir.expanduser().resolve()
    if not study_dir.exists():
        raise FileNotFoundError(study_dir)

    try:
        running_processes = find_study_processes(study_dir)
    except Exception:
        running_processes = []
    live_workers = _live_workers_for_study(study_dir, running_processes)
    active_relaunch_tasks = _active_relaunch_tasks_for_study(study_dir, running_processes)
    website_worker_status = _website_worker_status_for_study(study_dir, running_processes)

    now = datetime.now(tz=UTC).timestamp()
    study_pickle = study_dir / "study.pkl.gz"
    planned_tasks = _task_entries_from_study_pickle(study_pickle)
    planned_task_map = {task["task_id"]: task for task in planned_tasks}
    worker_map = _planned_worker_map(study_dir)
    experiment_dirs = _iter_experiment_dirs(study_dir)

    experiments_by_task: dict[str, Path] = {}
    for exp_dir in experiment_dirs:
        task_id = _extract_task_id_from_exp_dir(exp_dir.name)
        experiments_by_task[task_id] = _preferred_exp_dir(experiments_by_task.get(task_id), exp_dir)

    all_task_ids = list(planned_task_map)
    for task_id in sorted(experiments_by_task):
        if task_id not in planned_task_map:
            all_task_ids.append(task_id)

    task_records: list[StudyTaskRecord] = []
    for fallback_order, task_id in enumerate(all_task_ids):
        task_meta = planned_task_map.get(task_id, {})
        exp_dir = experiments_by_task.get(task_id)
        worker = worker_map.get(task_id)
        if exp_dir is not None and worker is None:
            worker = _worker_name_for_exp_dir(study_dir, exp_dir)
        worker = worker or "main"

        reward = None
        n_steps = None
        observed_steps = 0
        err_msg = None
        started_at = None
        updated_at = None
        elapsed_seconds = None
        artifacts = {"log": None, "summary": None, "dag_html": None}
        status = "pending"
        relative_exp_dir = None

        if exp_dir is not None:
            relative_exp_dir = str(exp_dir.relative_to(study_dir))
            exp_args_path = exp_dir / "exp_args.pkl"
            summary_path = exp_dir / "summary_info.json"
            log_path = exp_dir / "experiment.log"
            dag_html_path = exp_dir / "dag_trace.html"
            step_files = sorted(exp_dir.glob("step_*.pkl.gz"))

            observed_steps = len(step_files)
            artifacts["log"] = relative_exp_dir + "/experiment.log" if log_path.exists() else None
            artifacts["summary"] = (
                relative_exp_dir + "/summary_info.json" if summary_path.exists() else None
            )
            artifacts["dag_html"] = (
                relative_exp_dir + "/dag_trace.html" if dag_html_path.exists() else None
            )
            started_ts = _earliest_mtime([exp_args_path, exp_dir, log_path, *step_files, summary_path])

            if summary_path.exists():
                try:
                    summary = json.loads(summary_path.read_text())
                except json.JSONDecodeError:
                    summary = {}
                reward = _safe_float(summary.get("cum_reward"))
                err_msg = summary.get("err_msg")
                raw_steps = summary.get("n_steps")
                try:
                    n_steps = None if raw_steps is None else int(raw_steps)
                except (TypeError, ValueError):
                    n_steps = None
                status = _task_status_from_summary(summary)
            elif log_path.exists() or step_files:
                updated_ts = _latest_mtime([exp_dir, log_path, *step_files])
                recently_active = (
                    updated_ts is not None
                    and now - updated_ts <= RECENT_INCOMPLETE_RUN_SECONDS
                )
                status = (
                    "running" if worker in live_workers or recently_active else "stopped"
                )

            if task_id in active_relaunch_tasks:
                relaunch_worker = active_relaunch_tasks[task_id]["worker"]
                if worker == "main" or worker == relaunch_worker:
                    worker = relaunch_worker
                status = "running"

            updated_ts = _latest_mtime([exp_dir, summary_path, log_path, *step_files])
            if status != "pending":
                started_at = isoformat_timestamp(started_ts)
                updated_at = isoformat_timestamp(updated_ts)
                elapsed_seconds = _elapsed_seconds(
                    started_ts,
                    updated_ts if status in {"passed", "partial", "failed", "stopped"} else now,
                )

        if task_id in active_relaunch_tasks:
            relaunch_worker = active_relaunch_tasks[task_id]["worker"]
            if worker == "main" or worker == relaunch_worker:
                worker = relaunch_worker
            status = "running"
            if updated_at is None:
                updated_at = isoformat_timestamp(now)
            if elapsed_seconds is None:
                elapsed_seconds = 0.0

        task_records.append(
            StudyTaskRecord(
                task_id=task_id,
                task_name=task_meta.get("task_name"),
                order=int(task_meta.get("order", fallback_order)),
                worker=worker,
                status=status,
                started_at=started_at,
                reward=reward,
                n_steps=n_steps,
                observed_steps=observed_steps,
                updated_at=updated_at,
                elapsed_seconds=elapsed_seconds,
                err_msg=err_msg,
                exp_relative_dir=relative_exp_dir,
                artifacts={key: value for key, value in artifacts.items() if value},
                sites=list(task_meta.get("sites") or []),
            )
        )

    task_records.sort(key=lambda record: (record.order, record.task_id))
    website_worker_status = _infer_website_worker_allocations_from_tasks(
        website_worker_status,
        task_records,
    )

    counts = defaultdict(int)
    completed_successes = []
    workers: dict[str, dict[str, Any]] = {}
    for record in task_records:
        counts[record.status] += 1
        if record.status in {"passed", "partial", "failed", "error"}:
            completed_successes.append(1.0 if record.status == "passed" else 0.0)
        worker_summary = workers.setdefault(
            record.worker,
            {
                "worker": record.worker,
                "total_tasks": 0,
                "pending_tasks": 0,
                "running_tasks": 0,
                "stopped_tasks": 0,
                "completed_tasks": 0,
                "passed_tasks": 0,
                "partial_tasks": 0,
                "failed_tasks": 0,
                "error_tasks": 0,
                "started_at": None,
                "updated_at": None,
                "elapsed_seconds": None,
            },
        )
        worker_summary["total_tasks"] += 1
        if record.status == "pending":
            worker_summary["pending_tasks"] += 1
        elif record.status == "running":
            worker_summary["running_tasks"] += 1
        elif record.status == "stopped":
            worker_summary["stopped_tasks"] += 1
        elif record.status in {"passed", "partial", "failed", "error"}:
            worker_summary["completed_tasks"] += 1
            worker_summary[f"{record.status}_tasks"] += 1

        if record.updated_at is not None:
            if worker_summary["updated_at"] is None or record.updated_at > worker_summary["updated_at"]:
                worker_summary["updated_at"] = record.updated_at
        if record.started_at is not None:
            if worker_summary["started_at"] is None or record.started_at < worker_summary["started_at"]:
                worker_summary["started_at"] = record.started_at

    for worker_summary in workers.values():
        if worker_summary["started_at"] is not None:
            start_dt = datetime.fromisoformat(worker_summary["started_at"]).timestamp()
            if worker_summary["running_tasks"] == 0 and worker_summary["pending_tasks"] == 0:
                end_iso = worker_summary["updated_at"]
                end_dt = datetime.fromisoformat(end_iso).timestamp() if end_iso else now
            else:
                end_dt = now
            worker_summary["elapsed_seconds"] = _elapsed_seconds(start_dt, end_dt)

    completed_count = counts["passed"] + counts["partial"] + counts["failed"] + counts["error"]
    total_count = len(task_records)
    progress_pct = round((completed_count / total_count) * 100, 1) if total_count else 0.0
    is_parallel = (
        (study_dir / "workers").exists()
        or (study_dir / "tasks").exists()
        or bool(website_worker_status["sites"])
    )
    study_started_ts = _earliest_mtime([study_pickle, study_dir])
    study_updated_ts = _latest_mtime([study_dir, study_pickle, *experiment_dirs])

    return {
        "study": {
            "name": _study_name_from_pickle(study_pickle, study_dir.name),
            "path": str(study_dir),
            "is_parallel": is_parallel,
            "running_pids": [process["pid"] for process in running_processes],
            "can_stop": bool(running_processes),
            "started_at": isoformat_timestamp(study_started_ts),
            "updated_at": isoformat_timestamp(study_updated_ts),
            "elapsed_seconds": _elapsed_seconds(
                study_started_ts,
                study_updated_ts
                if counts["running"] == 0 and counts["pending"] == 0 and total_count > 0
                else now,
            ),
            "total_tasks": total_count,
            "pending_tasks": counts["pending"],
            "running_tasks": counts["running"],
            "stopped_tasks": counts["stopped"],
            "completed_tasks": completed_count,
            "passed_tasks": counts["passed"],
            "partial_tasks": counts["partial"],
            "failed_tasks": counts["failed"],
            "error_tasks": counts["error"],
            "avg_reward": round(sum(completed_successes) / len(completed_successes), 3)
            if completed_successes
            else None,
            "progress_pct": progress_pct,
        },
        "workers": sorted(workers.values(), key=lambda item: item["worker"]),
        "website_workers": website_worker_status,
        "tasks": [
            {
                "task_id": record.task_id,
                "task_name": record.task_name,
                "order": record.order,
                "worker": record.worker,
                "status": record.status,
                "started_at": record.started_at,
                "reward": record.reward,
                "n_steps": record.n_steps,
                "observed_steps": record.observed_steps,
                "updated_at": record.updated_at,
                "elapsed_seconds": record.elapsed_seconds,
                "err_msg": record.err_msg,
                "exp_relative_dir": record.exp_relative_dir,
                "artifacts": record.artifacts,
            }
            for record in task_records
        ],
    }


def _study_card(study_dir: Path) -> dict[str, Any]:
    snapshot = build_run_snapshot(study_dir)
    return {
        "name": snapshot["study"]["name"],
        "path": snapshot["study"]["path"],
        "is_parallel": snapshot["study"]["is_parallel"],
        "running_pids": snapshot["study"]["running_pids"],
        "can_stop": snapshot["study"]["can_stop"],
        "updated_at": snapshot["study"]["updated_at"],
        "elapsed_seconds": snapshot["study"]["elapsed_seconds"],
        "total_tasks": snapshot["study"]["total_tasks"],
        "completed_tasks": snapshot["study"]["completed_tasks"],
        "running_tasks": snapshot["study"]["running_tasks"],
        "pending_tasks": snapshot["study"]["pending_tasks"],
        "stopped_tasks": snapshot["study"]["stopped_tasks"],
        "passed_tasks": snapshot["study"]["passed_tasks"],
        "partial_tasks": snapshot["study"]["partial_tasks"],
        "failed_tasks": snapshot["study"]["failed_tasks"],
        "error_tasks": snapshot["study"]["error_tasks"],
        "progress_pct": snapshot["study"]["progress_pct"],
    }


INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>WebArena-Pro Run Dashboard</title>
  <style>
    :root {
      --bg: #f5f7fa;
      --panel: #ffffff;
      --panel-muted: #fbfcfe;
      --line: #dbe2ea;
      --line-strong: #c5d0dc;
      --ink: #16202a;
      --muted: #5d6b7a;
      --accent: #2563eb;
      --success: #15803d;
      --warning: #b45309;
      --danger: #b42318;
      --running: #2563eb;
      --shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      min-height: 100vh;
    }

    .shell {
      display: grid;
      grid-template-columns: 300px 1fr;
      gap: 16px;
      min-height: 100vh;
      padding: 16px;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      box-shadow: var(--shadow);
    }

    .sidebar {
      padding: 18px;
      position: sticky;
      top: 16px;
      height: calc(100vh - 32px);
      overflow: auto;
    }

    .brand {
      margin-bottom: 16px;
    }

    .eyebrow {
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 6px;
      font-weight: 700;
    }

    h1, h2, h3 {
      margin: 0;
      font-weight: 700;
    }

    h1 { font-size: 24px; line-height: 1.2; }
    h2 { font-size: 22px; margin-bottom: 6px; }
    h3 { font-size: 16px; }

    .hint, .meta {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }

    .study-list {
      display: grid;
      gap: 10px;
      margin-top: 16px;
    }

    .study-card {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 12px;
      background: var(--panel);
      cursor: pointer;
      transition: border-color 140ms ease, background 140ms ease;
    }

    .study-card:hover { border-color: var(--line-strong); background: var(--panel-muted); }
    .study-card.active {
      background: #eff6ff;
      border-color: #93c5fd;
    }

    .study-card .title {
      font-weight: 700;
      font-size: 14px;
      line-height: 1.25;
      margin-bottom: 6px;
      word-break: break-word;
    }

    .study-card .stats {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      font-size: 12px;
      color: var(--muted);
    }

    .content {
      display: grid;
      gap: 16px;
      align-content: start;
    }

    .hero {
      padding: 20px;
      background: var(--panel);
    }

    .hero-grid, .metric-grid, .worker-grid, .website-worker-grid {
      display: grid;
      gap: 12px;
    }

    .hero-grid {
      grid-template-columns: 2fr 1fr;
      align-items: start;
    }

    .metric-grid {
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    }

    .metric {
      padding: 14px;
      border-radius: 10px;
      background: var(--panel-muted);
      border: 1px solid var(--line);
    }

    .metric .label {
      font-size: 12px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 6px;
      font-weight: 700;
    }

    .metric .value {
      font-size: 24px;
      font-weight: 700;
      line-height: 1;
    }

    .row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }

    .badge {
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 11px;
      font-weight: 700;
      border: 1px solid var(--line);
      background: var(--panel-muted);
    }

    .badge.parallel { background: #eff6ff; color: var(--running); border-color: #bfdbfe; }
    .badge.serial { background: #f8fafc; color: var(--muted); border-color: var(--line); }
    .status-passed, .status-pill.passed { color: var(--success); background: #ecfdf3; border-color: #bbf7d0; }
    .status-partial, .status-pill.partial { color: var(--warning); background: #fff7ed; border-color: #fed7aa; }
    .status-failed, .status-pill.failed { color: var(--danger); background: #fef3f2; border-color: #fecdca; }
    .status-pill.error { color: #9f1239; background: #fff1f2; border-color: #fecdd3; }
    .status-running, .status-pill.running { color: var(--running); background: #eff6ff; border-color: #bfdbfe; }
    .status-pending, .status-pill.pending { color: var(--muted); background: #f8fafc; border-color: var(--line); }
    .status-stopped, .status-pill.stopped { color: #7a271a; background: #fff1eb; border-color: #f7bfa7; }
    .status-pill.busy { color: #7c2d12; background: #fff7ed; border-color: #fed7aa; }
    .status-pill.idle, .status-pill.healthy { color: var(--success); background: #ecfdf3; border-color: #bbf7d0; }
    .status-pill.starting, .status-pill.created, .status-pill.restarting { color: var(--warning); background: #fffbeb; border-color: #fde68a; }
    .status-pill.resetting { color: #7c2d12; background: #fff7ed; border-color: #fed7aa; }
    .status-pill.stopping { color: #7a271a; background: #fff1eb; border-color: #f7bfa7; }
    .status-pill.unhealthy { color: var(--danger); background: #fef3f2; border-color: #fecdca; }
    .status-pill.unknown { color: var(--muted); background: #f8fafc; border-color: var(--line); }
    .status-pill.free { color: var(--success); background: #ecfdf3; border-color: #bbf7d0; }
    .status-pill.in-use { color: var(--running); background: #eff6ff; border-color: #bfdbfe; }

    .section {
      padding: 20px;
    }

    .section-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: end;
      margin-bottom: 14px;
    }

    .worker-grid {
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }

    .worker-card {
      padding: 14px;
      border-radius: 10px;
      background: var(--panel-muted);
      border: 1px solid var(--line);
    }

    .website-worker-grid {
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    }

    .website-worker-card {
      padding: 14px;
      border-radius: 10px;
      background: var(--panel-muted);
      border: 1px solid var(--line);
    }

    .website-worker-row {
      display: grid;
      grid-template-columns: minmax(82px, 1fr) auto auto minmax(86px, 1fr);
      gap: 8px;
      align-items: center;
      padding: 8px 0;
      border-top: 1px solid #edf2f7;
      min-width: 0;
    }

    .website-worker-row:first-of-type {
      border-top: 0;
    }

    .website-worker-row > * {
      min-width: 0;
    }

    .progress {
      height: 8px;
      background: #e8edf3;
      border-radius: 999px;
      overflow: hidden;
      margin-top: 10px;
    }

    .progress > div {
      height: 100%;
      background: var(--accent);
      border-radius: inherit;
    }

    .toolbar {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }

    button, .linkish {
      appearance: none;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      border-radius: 8px;
      padding: 8px 12px;
      font: inherit;
      cursor: pointer;
      text-decoration: none;
    }

    button:hover, .linkish:hover { border-color: var(--line-strong); background: var(--panel-muted); }

    .danger-button {
      color: var(--danger);
      border-color: #fecdca;
      background: #fef3f2;
    }

    .danger-button:hover {
      border-color: #fda29b;
      background: #fee4e2;
    }

    input, select, textarea {
      font: inherit;
      padding: 8px 10px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--panel);
      min-width: 120px;
    }

    textarea {
      min-height: 140px;
      resize: vertical;
      width: 100%;
    }

    .field {
      display: grid;
      gap: 6px;
      font-size: 13px;
      color: var(--muted);
    }

    .field strong {
      color: var(--ink);
      font-size: 13px;
    }

    .field-wide {
      grid-column: 1 / -1;
    }

    .status-banner {
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: var(--panel-muted);
      font-size: 13px;
    }

    .status-ok {
      color: var(--success);
      background: #ecfdf3;
      border-color: #bbf7d0;
    }

    .status-error {
      color: var(--danger);
      background: #fef3f2;
      border-color: #fecdca;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }

    th, td {
      padding: 10px 8px;
      border-bottom: 1px solid #edf2f7;
      text-align: left;
      vertical-align: top;
    }

    th {
      color: var(--muted);
      font-size: 11px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }

    .task-title {
      font-weight: 700;
      margin-bottom: 2px;
    }

    .actions {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }

    .empty {
      padding: 40px 24px;
      text-align: center;
      color: var(--muted);
    }

    .loading {
      animation: pulse 1.4s ease-in-out infinite;
    }

    @keyframes pulse {
      0%, 100% { opacity: 0.72; }
      50% { opacity: 1; }
    }

    @media (max-width: 1024px) {
      .shell { grid-template-columns: 1fr; }
      .sidebar { position: static; height: auto; }
      .hero-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="panel sidebar">
      <div class="brand">
        <div class="eyebrow">Run Monitor</div>
        <h1>WebArena-Pro dashboard</h1>
        <p class="hint">Auto-refreshing study progress with worker and task-level status.</p>
      </div>
      <div class="toolbar">
        <button id="refresh-studies">Refresh list</button>
      </div>
      <div class="meta" id="results-root"></div>
      <div class="study-list" id="study-list">
        <div class="loading">Loading studies…</div>
      </div>
    </aside>

    <main class="content">
      <section class="panel hero" id="hero">
        <div class="loading">Loading study…</div>
      </section>

      <section class="panel section">
        <div class="section-head">
          <div>
            <div class="eyebrow">Workers</div>
            <h3>Parallel lanes</h3>
          </div>
        </div>
        <div class="worker-grid" id="worker-grid">
          <div class="loading">Loading workers…</div>
        </div>
      </section>

      <section class="panel section">
        <div class="section-head">
          <div>
            <div class="eyebrow">Websites</div>
            <h3>Website workers</h3>
          </div>
          <div class="meta" id="website-worker-meta"></div>
        </div>
        <div class="website-worker-grid" id="website-worker-grid">
          <div class="loading">Loading website workers…</div>
        </div>
      </section>

      <section class="panel section">
        <div class="section-head">
          <div>
            <div class="eyebrow">Tasks</div>
            <h3>Task-level progress</h3>
          </div>
          <div class="toolbar">
            <select id="status-filter">
              <option value="all">All statuses</option>
              <option value="pending">Pending</option>
              <option value="running">Running</option>
              <option value="stopped">Stopped</option>
              <option value="passed">Passed</option>
              <option value="partial">Partial</option>
              <option value="failed">Failed</option>
              <option value="error">Errored</option>
            </select>
            <input id="task-search" type="search" placeholder="Filter task id or name" />
          </div>
        </div>
        <div id="task-table-wrap">
          <div class="loading">Loading tasks…</div>
        </div>
      </section>
    </main>
  </div>

  <script>
    const params = new URLSearchParams(window.location.search);
    let selectedStudy = params.get("study_dir");
    let studies = [];
    let currentSnapshot = null;
    let studyActionStatus = null;

    function esc(value) {
      return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
    }

    function statusClass(value) {
      return String(value ?? "unknown").toLowerCase().replace(/[^a-z0-9_-]/g, "-");
    }

    function relativeTime(value) {
      if (!value) return "—";
      const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000);
      if (!Number.isFinite(seconds)) return value;
      if (Math.abs(seconds) < 60) return `${seconds}s ago`;
      const minutes = Math.round(seconds / 60);
      if (Math.abs(minutes) < 60) return `${minutes}m ago`;
      const hours = Math.round(minutes / 60);
      if (Math.abs(hours) < 24) return `${hours}h ago`;
      const days = Math.round(hours / 24);
      return `${days}d ago`;
    }

    function formatDuration(value) {
      if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
      const totalSeconds = Math.max(0, Math.round(Number(value)));
      const hours = Math.floor(totalSeconds / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      const seconds = totalSeconds % 60;
      if (hours > 0) return `${hours}h ${minutes}m`;
      if (minutes > 0) return `${minutes}m ${seconds}s`;
      return `${seconds}s`;
    }

    function artifactUrl(path) {
      const search = new URLSearchParams({ study_dir: selectedStudy, path });
      return `/artifact?${search.toString()}`;
    }

    function setStudyActionStatus(kind, message) {
      studyActionStatus = message ? { kind, message } : null;
      if (currentSnapshot) {
        renderHero(currentSnapshot);
      }
    }

    function renderStudies(data) {
      studies = data.studies;
      document.getElementById("results-root").textContent = data.results_root;
      if (!selectedStudy && studies.length) {
        selectedStudy = studies[0].path;
      }

      const html = studies.length
        ? studies.map(study => {
            const active = study.path === selectedStudy ? " active" : "";
            const mode = study.is_parallel ? "parallel" : "serial";
            const stopButton = study.can_stop
              ? `<button class="danger-button stop-study-card" data-path="${esc(study.path)}">Stop</button>`
              : "";
            return `
              <div class="study-card${active}" data-path="${esc(study.path)}">
                <div class="title">${esc(study.name)}</div>
                <div class="stats">
                  <span class="badge ${mode}">${study.is_parallel ? "parallel" : "single"}</span>
                  <span>${study.completed_tasks}/${study.total_tasks} done</span>
                  <span>${study.running_tasks} running</span>
                  <span>${study.pending_tasks} pending</span>
                  <span>${study.stopped_tasks} stopped</span>
                  <span>${study.error_tasks} errored</span>
                  <span>${formatDuration(study.elapsed_seconds)}</span>
                </div>
                <div class="toolbar" style="margin-top:8px;">${stopButton}</div>
                <div class="meta" style="margin-top:8px;">Updated ${relativeTime(study.updated_at)}</div>
              </div>
            `;
          }).join("")
        : `<div class="empty">No studies found under the results directory.</div>`;

      const node = document.getElementById("study-list");
      node.innerHTML = html;
      node.querySelectorAll(".study-card").forEach(card => {
        card.addEventListener("click", () => {
          selectedStudy = card.dataset.path;
          const next = new URL(window.location.href);
          next.searchParams.set("study_dir", selectedStudy);
          window.history.replaceState({}, "", next);
          renderStudies({ studies, results_root: data.results_root });
          loadSnapshot();
        });
      });
      node.querySelectorAll(".stop-study-card").forEach(button => {
        button.addEventListener("click", async (event) => {
          event.stopPropagation();
          await stopStudy(button.dataset.path);
        });
      });
    }

    function renderHero(snapshot) {
      const study = snapshot.study;
      const modeClass = study.is_parallel ? "parallel" : "serial";
      const stopControl = study.can_stop
        ? `<button id="stop-selected-study" class="danger-button">Stop study</button>`
        : "";
      const actionBanner = studyActionStatus
        ? `<div class="status-banner ${studyActionStatus.kind === "error" ? "status-error" : "status-ok"}" style="margin-top:14px;">${esc(studyActionStatus.message)}</div>`
        : "";
      document.getElementById("hero").innerHTML = `
        <div class="hero-grid">
          <div>
            <div class="eyebrow">Live Study</div>
            <h2>${esc(study.name)}</h2>
            <div class="row" style="margin:10px 0 14px;">
              <span class="badge ${modeClass}">${study.is_parallel ? "parallel run" : "single-process run"}</span>
              <span class="meta">${esc(study.path)}</span>
            </div>
            <div class="meta">Updated ${relativeTime(study.updated_at)} • running for ${formatDuration(study.elapsed_seconds)} • ${study.progress_pct}% complete</div>
            <div class="toolbar" style="margin-top:14px;">${stopControl}</div>
            ${actionBanner}
          </div>
          <div class="metric">
            <div class="label">Elapsed</div>
            <div class="value">${formatDuration(study.elapsed_seconds)}</div>
          </div>
        </div>
        <div class="metric-grid" style="margin-top:18px;">
          <div class="metric"><div class="label">Average Reward</div><div class="value">${study.avg_reward ?? "—"}</div></div>
          <div class="metric"><div class="label">Total</div><div class="value">${study.total_tasks}</div></div>
          <div class="metric"><div class="label">Completed</div><div class="value">${study.completed_tasks}</div></div>
          <div class="metric"><div class="label">Running</div><div class="value">${study.running_tasks}</div></div>
          <div class="metric"><div class="label">Pending</div><div class="value">${study.pending_tasks}</div></div>
          <div class="metric"><div class="label">Stopped</div><div class="value">${study.stopped_tasks}</div></div>
          <div class="metric"><div class="label">Passed</div><div class="value">${study.passed_tasks}</div></div>
          <div class="metric"><div class="label">Failed</div><div class="value">${study.failed_tasks}</div></div>
          <div class="metric"><div class="label">Errored</div><div class="value">${study.error_tasks}</div></div>
        </div>
      `;
      const stopButton = document.getElementById("stop-selected-study");
      if (stopButton) {
        stopButton.addEventListener("click", async () => {
          await stopStudy(study.path);
        });
      }
    }

    function renderWorkers(snapshot) {
      const workers = snapshot.workers;
      document.getElementById("worker-grid").innerHTML = workers.length
        ? workers.map(worker => {
            const pct = worker.total_tasks ? Math.round((worker.completed_tasks / worker.total_tasks) * 100) : 0;
            return `
              <div class="worker-card">
                <div class="row" style="justify-content:space-between;">
                  <h3>${esc(worker.worker)}</h3>
                  <span class="meta">${relativeTime(worker.updated_at)}</span>
                </div>
                <div class="meta" style="margin-top:6px;">
                  ${worker.completed_tasks}/${worker.total_tasks} done • ${worker.running_tasks} running • ${worker.pending_tasks} pending • ${worker.stopped_tasks} stopped • ${formatDuration(worker.elapsed_seconds)}
                </div>
                <div class="progress"><div style="width:${pct}%;"></div></div>
                <div class="row" style="margin-top:12px;">
                  <span class="badge status-pill passed">${worker.passed_tasks} pass</span>
                  <span class="badge status-pill partial">${worker.partial_tasks} partial</span>
                  <span class="badge status-pill failed">${worker.failed_tasks} fail</span>
                  <span class="badge status-pill error">${worker.error_tasks} error</span>
                  <span class="badge status-pill stopped">${worker.stopped_tasks} stopped</span>
                </div>
              </div>
            `;
          }).join("")
        : `<div class="empty">No worker-specific information yet.</div>`;
    }

    function renderWebsiteWorkers(snapshot) {
      const status = snapshot.website_workers || { sites: [] };
      const sites = status.sites || [];
      const meta = document.getElementById("website-worker-meta");
      meta.textContent = sites.length
        ? `${status.source || "unknown"} • ${status.worker_count ?? "?"} per website • updated ${relativeTime(status.updated_at)}`
        : "";

      document.getElementById("website-worker-grid").innerHTML = sites.length
        ? sites.map(site => {
            const workers = site.workers || [];
            const lifecycleCounts = Object.entries(site.lifecycle_counts || site.counts || {})
              .map(([name, count]) => `<span class="badge status-pill ${statusClass(name)}">${esc(count)} ${esc(name)}</span>`)
              .join("");
            const allocationCounts = Object.entries(site.allocation_counts || {})
              .map(([name, count]) => `<span class="badge status-pill ${statusClass(name)}">${esc(count)} ${esc(name)}</span>`)
              .join("");
            const rows = workers.map(worker => {
              const detail = worker.task_id !== null && worker.task_id !== undefined
                ? `task ${worker.task_id}`
                : (worker.health || worker.container_status || worker.container_name || "—");
              const lifecycleStatus = worker.lifecycle_status || worker.status || "unknown";
              const allocationStatus = worker.allocation_status || (worker.in_use ? "in-use" : "free");
              return `
                <div class="website-worker-row">
                  <strong>${esc(worker.worker || `${site.site}-w${worker.worker_index ?? "?"}`)}</strong>
                  <span class="badge status-pill ${statusClass(lifecycleStatus)}">${esc(lifecycleStatus)}</span>
                  <span class="badge status-pill ${statusClass(allocationStatus)}">${esc(allocationStatus)}</span>
                  <span class="meta">${esc(detail)}</span>
                </div>
              `;
            }).join("");

            return `
              <div class="website-worker-card">
                <div class="row" style="justify-content:space-between;">
	                  <h3>${esc(site.site)}</h3>
	                  <span class="meta">${site.remaining_tasks ?? "—"} remaining</span>
	                </div>
	                <div class="row" style="margin:10px 0 4px;">${lifecycleCounts}</div>
	                <div class="row" style="margin:0 0 8px;">${allocationCounts}</div>
	                ${rows}
	              </div>
            `;
          }).join("")
        : `<div class="empty">No website-worker information yet.</div>`;
    }

    function renderTasks(snapshot) {
      const filter = document.getElementById("status-filter").value;
      const query = document.getElementById("task-search").value.trim().toLowerCase();
      const tasks = snapshot.tasks.filter(task => {
        if (filter !== "all" && task.status !== filter) return false;
        if (!query) return true;
        return String(task.task_id).toLowerCase().includes(query)
          || String(task.task_name ?? "").toLowerCase().includes(query)
          || String(task.worker).toLowerCase().includes(query);
      });

      if (!tasks.length) {
        document.getElementById("task-table-wrap").innerHTML = `<div class="empty">No tasks match the current filter.</div>`;
        return;
      }

      const rows = tasks.map(task => {
        const actions = [];
        if (task.artifacts.log) {
          actions.push(`<a class="linkish" target="_blank" href="${artifactUrl(task.artifacts.log)}">log</a>`);
        }
        if (task.artifacts.summary) {
          actions.push(`<a class="linkish" target="_blank" href="${artifactUrl(task.artifacts.summary)}">summary</a>`);
        }
        if (task.artifacts.dag_html) {
          actions.push(`<a class="linkish" target="_blank" href="${artifactUrl(task.artifacts.dag_html)}">dag</a>`);
        }

        return `
          <tr>
            <td>
              <div class="task-title">${esc(task.task_id)}</div>
              <div class="meta">${esc(task.task_name ?? "")}</div>
            </td>
            <td><span class="badge status-pill ${esc(task.status)}">${esc(task.status)}</span></td>
            <td>${esc(task.worker)}</td>
            <td>${formatDuration(task.status === "pending" ? null : task.elapsed_seconds)}</td>
            <td>${task.reward ?? "—"}</td>
            <td>${task.n_steps ?? task.observed_steps}</td>
            <td>${relativeTime(task.updated_at)}</td>
            <td>${task.err_msg ? `<span class="meta">${esc(task.err_msg.slice(0, 120))}</span>` : "—"}</td>
            <td><div class="actions">${actions.join("") || "—"}</div></td>
          </tr>
        `;
      }).join("");

      document.getElementById("task-table-wrap").innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Task</th>
              <th>Status</th>
              <th>Worker</th>
              <th>Elapsed</th>
              <th>Reward</th>
              <th>Steps</th>
              <th>Updated</th>
              <th>Notes</th>
              <th>Artifacts</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }

    async function loadStudies() {
      const response = await fetch("/api/studies");
      const data = await response.json();
      renderStudies(data);
    }

    async function loadSnapshot() {
      if (!selectedStudy) return;
      const response = await fetch(`/api/run?study_dir=${encodeURIComponent(selectedStudy)}`);
      if (!response.ok) {
        const detail = await response.text();
        document.getElementById("hero").innerHTML = `<div class="empty">Could not load study snapshot.<br>${esc(detail)}</div>`;
        document.getElementById("worker-grid").innerHTML = "";
        document.getElementById("website-worker-grid").innerHTML = "";
        document.getElementById("website-worker-meta").textContent = "";
        document.getElementById("task-table-wrap").innerHTML = "";
        return;
      }
      currentSnapshot = await response.json();
      renderHero(currentSnapshot);
      renderWorkers(currentSnapshot);
      renderWebsiteWorkers(currentSnapshot);
      renderTasks(currentSnapshot);
    }

    async function stopStudy(studyDir) {
      if (!studyDir) return;
      if (!window.confirm("Stop this study and terminate its running evaluation process?")) return;

      setStudyActionStatus("ok", "Stopping study…");
      try {
        const response = await fetch("/api/studies/stop", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ study_dir: studyDir }),
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Could not stop study.");
        }

        setStudyActionStatus(
          "ok",
          data.stopped_pids.length
            ? `Stopped study. Signaled PID${data.stopped_pids.length === 1 ? "" : "s"} ${data.stopped_pids.join(", ")}.`
            : "No running study process was found."
        );
        await loadStudies();
        await loadSnapshot();
      } catch (error) {
        setStudyActionStatus("error", error.message || String(error));
      }
    }

    document.getElementById("refresh-studies").addEventListener("click", async () => {
      await loadStudies();
      await loadSnapshot();
    });
    document.getElementById("status-filter").addEventListener("change", () => currentSnapshot && renderTasks(currentSnapshot));
    document.getElementById("task-search").addEventListener("input", () => currentSnapshot && renderTasks(currentSnapshot));

    Promise.resolve()
      .then(loadStudies)
      .then(loadSnapshot)
      .catch(error => {
        document.getElementById("hero").innerHTML = `<div class="empty">Dashboard failed to load.<br>${esc(error.message || error)}</div>`;
      });

    setInterval(async () => {
      try {
        await loadStudies();
        await loadSnapshot();
      } catch (error) {
        console.error(error);
      }
    }, 3000);
  </script>
</body>
</html>
"""


def create_dashboard_app(
    results_root: Path | None = None,
    default_study: Path | None = None,
) -> FastAPI:
    resolved_root = (results_root or default_results_root()).expanduser().resolve()
    initial_study = default_study.expanduser().resolve() if default_study else None

    app = FastAPI(title="WebArena-Pro Dashboard")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(INDEX_HTML)

    @app.get("/api/studies", response_class=JSONResponse)
    def api_studies(limit: int = Query(default=20, ge=1, le=100)) -> JSONResponse:
        studies = [_study_card(path) for path in list_top_level_studies(resolved_root, limit=limit)]
        return JSONResponse({"results_root": str(resolved_root), "studies": studies})

    @app.post("/api/studies/stop", response_class=JSONResponse)
    def api_stop_study(payload: dict[str, str]) -> JSONResponse:
        study_dir = payload.get("study_dir", "")
        if not study_dir:
            raise HTTPException(status_code=400, detail="study_dir is required.")

        candidate = Path(study_dir).expanduser().resolve()
        if not candidate.exists():
            raise HTTPException(status_code=404, detail=f"Study not found: {candidate}")
        if not candidate.is_relative_to(resolved_root):
            raise HTTPException(status_code=403, detail="Study path escapes the results root.")

        try:
            result = stop_study_processes(candidate)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to stop study: {exc}") from exc

        return JSONResponse(
            {
                "study_dir": str(result["study_dir"]),
                "matched_pids": result["matched_pids"],
                "stopped_pids": result["stopped_pids"],
                "escalated_pids": result["escalated_pids"],
            }
        )

    @app.get("/api/run", response_class=JSONResponse)
    def api_run(study_dir: str | None = None) -> JSONResponse:
        candidate = Path(study_dir).expanduser() if study_dir else initial_study
        if candidate is None:
            recent = list_top_level_studies(resolved_root, limit=1)
            if not recent:
                raise HTTPException(status_code=404, detail="No studies found.")
            candidate = recent[0]
        try:
            snapshot = build_run_snapshot(candidate)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Study not found: {candidate}") from None
        return JSONResponse(snapshot)

    @app.get("/artifact")
    def artifact(study_dir: str, path: str) -> FileResponse:
        study_path = Path(study_dir).expanduser().resolve()
        if not study_path.exists():
            raise HTTPException(status_code=404, detail="Study directory does not exist.")

        target = (study_path / path).resolve()
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="Artifact not found.")
        if not target.is_relative_to(study_path):
            raise HTTPException(status_code=403, detail="Artifact path escapes the study directory.")

        media_type = None
        if target.suffix == ".json":
            media_type = "application/json"
        elif target.suffix == ".log":
            media_type = "text/plain"
        elif target.suffix == ".html":
            media_type = "text/html"

        return FileResponse(target, media_type=media_type, filename=target.name)

    return app
