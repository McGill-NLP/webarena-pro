from __future__ import annotations

import argparse
import copy
import gzip
import json
import os
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from webarena_pro_core.task import CONFIG_DIR
from webarena_pro_bgym.utils import has_ungraded_score
_EXP_TASK_ID_RE = re.compile(r"_on_webarena-pro-bgym\.([^_/]+)(?:_\d+)*$")
_SUBMISSION_TASK_ID_RE = re.compile(r"-submission-(\d+)$")


@dataclass
class SubmissionTask:
    site: str
    task_id: str
    task: dict[str, Any]
    source_dir: Path
    source_kind: str
    submitted_at: str | None = None
    run_status: str | None = None
    submission_status: str | None = None
    queue_status: str | None = None
    return_code: int | None = None
    reward: float | None = None
    verifier_verdict: str | None = None
    summary_path: Path | None = None
    submission_path: Path | None = None


@dataclass
class MergeStats:
    found: int = 0
    added: int = 0
    replaced: int = 0
    removed_archived: int = 0
    removed_review_excluded: int = 0
    removed_uncollected: int = 0
    removed_duplicates: int = 0
    skipped_existing: int = 0
    skipped_no_site: int = 0
    output_paths: list[Path] = field(default_factory=list)


@dataclass
class TaskReview:
    path: Path
    payload: dict[str, Any]


def _review_rating(payload: dict[str, Any], key: str) -> str | None:
    section = payload.get(key)
    if not isinstance(section, dict):
        return None
    rating = section.get("rating")
    if not isinstance(rating, str):
        return None
    rating = rating.strip().lower()
    return rating or None


def _is_review_excluded_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return (
        _review_rating(payload, "feasibility") == "infeasible"
        or _review_rating(payload, "ambiguity") == "ambiguous"
    )


def _is_review_excluded(review: TaskReview | None) -> bool:
    return review is not None and _is_review_excluded_payload(review.payload)


def _normalized_task_intent(task: dict[str, Any]) -> str | None:
    intent = _string_value(task.get("intent"))
    if intent is None:
        return None
    normalized = re.sub(r"\s+", " ", intent).casefold()
    return normalized or None


class _PicklePlaceholder:
    """Minimal object used when reading old AgentLab pickles without imports."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._pickle_args = args
        self._pickle_kwargs = kwargs

    def __setstate__(self, state: Any) -> None:
        if isinstance(state, dict):
            self.__dict__.update(state)
        else:
            self._pickle_state = state


class _SafeUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> Any:
        if module == "pathlib" and name in {"PosixPath", "WindowsPath"}:
            return Path
        return _PicklePlaceholder


def default_results_root() -> Path:
    env_root = os.environ.get("AGENTLAB_RESULTS_DIR")
    if env_root:
        return Path(env_root).expanduser()

    mounted_root = Path("/mnt/data/agentlab_results")
    if mounted_root.exists():
        return mounted_root

    return Path.home() / "agentlab_results"


def _load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_pickle(path: Path) -> Any | None:
    if not path.exists():
        return None

    try:
        with gzip.open(path, "rb") as handle:
            return _SafeUnpickler(handle).load()
    except Exception:
        pass

    try:
        with path.open("rb") as handle:
            return _SafeUnpickler(handle).load()
    except Exception:
        return None


def _task_site(task: dict[str, Any], submission: dict[str, Any] | None = None) -> str | None:
    sites = task.get("sites")
    if isinstance(sites, list) and sites:
        return str(sites[0])
    if task.get("website") is not None:
        return str(task["website"])
    if submission and submission.get("start_site") is not None:
        return str(submission["start_site"])
    return None


def _task_id(task: dict[str, Any]) -> str | None:
    value = task.get("task_id")
    if value is None:
        return None
    return str(value)


def _submission_dir_task_id(source_dir: Path) -> str | None:
    match = _SUBMISSION_TASK_ID_RE.search(source_dir.name)
    if match:
        return match.group(1)
    return None


def _status_from_reward(reward: float | None) -> str | None:
    if reward is None:
        return None
    if reward >= 1.0:
        return "passed"
    if reward > 0:
        return "partial"
    return "failed"


def _iter_submission_dirs(results_root: Path) -> list[Path]:
    if not results_root.exists():
        return []

    dirs: dict[Path, float] = {}
    for submission_path in results_root.rglob("submission.json"):
        parent = submission_path.parent
        dirs[parent] = parent.stat().st_mtime

    for child in results_root.iterdir():
        if child.is_dir() and "submission" in child.name.lower():
            dirs[child] = child.stat().st_mtime

    return sorted(dirs, key=lambda path: (dirs[path], path.name))


def _extract_task_id_from_exp_dir(exp_dir_name: str) -> str | None:
    match = _EXP_TASK_ID_RE.search(exp_dir_name)
    if match:
        return match.group(1)
    if "webarena-pro-bgym." not in exp_dir_name:
        return None
    return exp_dir_name.rsplit("webarena-pro-bgym.", 1)[-1].split("_", 1)[0]


def _best_summary_path(source_dir: Path, task_id: str | None) -> Path | None:
    summary_paths = sorted(source_dir.rglob("summary_info.json"))
    if not summary_paths:
        return None
    if task_id is not None:
        for path in summary_paths:
            exp_task_id = _extract_task_id_from_exp_dir(path.parent.name)
            if exp_task_id == task_id:
                return path
    if len(summary_paths) == 1:
        return summary_paths[0]
    return max(summary_paths, key=lambda path: path.stat().st_mtime)


def _summary_metadata(summary_path: Path | None) -> tuple[float | None, str | None]:
    if summary_path is None:
        return None, None
    summary = _load_json(summary_path)
    if not isinstance(summary, dict):
        return None, None
    reward = _safe_float(summary.get("cum_reward"))
    if has_ungraded_score(summary):
        return reward, "failed"
    return reward, _status_from_reward(reward)


def _verifier_verdict(source_dir: Path, task_id: str | None) -> str | None:
    candidates = sorted(source_dir.rglob("eval_results.json"))
    if task_id is not None:
        for path in candidates:
            exp_task_id = _extract_task_id_from_exp_dir(path.parent.name)
            if exp_task_id == task_id:
                payload = _load_json(path)
                if isinstance(payload, dict) and payload.get("final_verdict") is not None:
                    return str(payload["final_verdict"])

    for path in candidates:
        payload = _load_json(path)
        if isinstance(payload, dict) and payload.get("final_verdict") is not None:
            return str(payload["final_verdict"])
    return None


def _submission_timestamp(source_dir: Path, submission: dict[str, Any] | None) -> str | None:
    if submission:
        for key in ("created_at", "queued_at", "started_at", "finished_at"):
            if submission.get(key):
                return str(submission[key])
    return None


def _is_archived_submission(submission: dict[str, Any] | None) -> bool:
    if not submission:
        return False

    value = submission.get("archived")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _submission_metadata(
    *,
    source_dir: Path,
    source_kind: str,
    submission: dict[str, Any] | None,
    summary_path: Path | None,
    reward: float | None,
    run_status: str | None,
    verifier_verdict: str | None,
    review: TaskReview | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source": "agentlab_submission",
        "source_dir": str(source_dir),
        "source_kind": source_kind,
    }

    if submission:
        for key in (
            "created_at",
            "queued_at",
            "started_at",
            "finished_at",
            "queue_status",
            "status",
            "return_code",
            "creator_username",
            "creator_username_source",
            "agent_model",
            "judge_model",
            "worker_index",
            "container_name",
            "site_url",
            "reviewed",
            "reviewed_by",
            "reviewed_at",
            "reviewer_source",
        ):
            if submission.get(key) is not None:
                metadata[key] = submission[key]

    if summary_path is not None:
        metadata["summary_path"] = str(summary_path)
    if reward is not None:
        metadata["cum_reward"] = reward
    if run_status is not None:
        metadata["run_status"] = run_status
    if verifier_verdict is not None:
        metadata["verifier_verdict"] = verifier_verdict

    if review is not None:
        metadata["reviewed"] = True
        metadata["review_path"] = str(review.path)
        if review.payload.get("reviewer") is not None:
            metadata["reviewed_by"] = review.payload["reviewer"]
        for key in ("reviewer", "reviewer_source", "reviewed_at"):
            if review.payload.get(key) is not None:
                metadata[key] = review.payload[key]

    return metadata


def _string_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _latest_task_review(source_dir: Path, reviews_root: Path | None) -> TaskReview | None:
    if reviews_root is None:
        return None

    review_dir = reviews_root / source_dir.name
    if not review_dir.exists():
        return None

    reviews: list[TaskReview] = []
    for path in sorted(review_dir.glob("*.json")):
        payload = _load_json(path)
        if isinstance(payload, dict):
            reviews.append(TaskReview(path=path, payload=payload))

    if not reviews:
        return None

    def sort_key(review: TaskReview) -> tuple[str, float, str]:
        try:
            mtime = review.path.stat().st_mtime
        except OSError:
            mtime = 0.0
        reviewed_at = _string_value(review.payload.get("reviewed_at")) or ""
        return (reviewed_at, mtime, str(review.path))

    return max(reviews, key=sort_key)


def _apply_review_to_task(task: dict[str, Any], review: TaskReview | None) -> bool:
    if review is None:
        return False

    changed = False
    task_intent = _string_value(review.payload.get("task_intent"))
    if task_intent is not None and task.get("intent") != task_intent:
        task["intent"] = task_intent
        changed = True

    rubrics = review.payload.get("rubrics")
    if isinstance(rubrics, list):
        eval_cfg = task.get("eval")
        if not isinstance(eval_cfg, dict):
            eval_cfg = task.get("evaluation")
        if not isinstance(eval_cfg, dict):
            eval_cfg = {}
            task["eval"] = eval_cfg

        reviewed_rubrics = copy.deepcopy(rubrics)
        if eval_cfg.get("rubrics") != reviewed_rubrics:
            eval_cfg["rubrics"] = reviewed_rubrics
            changed = True

    return changed


def _mark_submission_reviewed(
    submission_path: Path,
    submission: dict[str, Any],
    review: TaskReview | None,
    *,
    exact_task_id: str | None = None,
    write: bool,
) -> dict[str, Any]:
    if review is None and exact_task_id is None:
        return submission

    updated = copy.deepcopy(submission)
    changed = False

    if exact_task_id is not None and exact_task_id.startswith("2026"):
        if updated.get("task_id") != exact_task_id:
            updated["task_id"] = exact_task_id
            changed = True

        task = updated.get("task")
        if isinstance(task, dict) and task.get("task_id") != exact_task_id:
            task["task_id"] = exact_task_id
            changed = True

    if review is not None:
        if updated.get("reviewed") is not True:
            updated["reviewed"] = True
            changed = True

        field_map = {
            "reviewed_by": "reviewer",
            "reviewer_source": "reviewer_source",
            "reviewed_at": "reviewed_at",
        }
        for output_key, review_key in field_map.items():
            value = review.payload.get(review_key)
            if value is not None and updated.get(output_key) != value:
                updated[output_key] = value
                changed = True

        task = updated.get("task")
        if isinstance(task, dict):
            changed = _apply_review_to_task(task, review) or changed

    if changed and write:
        _write_json(submission_path, updated)

    return updated


def _make_submission_task(
    *,
    source_dir: Path,
    source_kind: str,
    raw_task: dict[str, Any],
    submission: dict[str, Any] | None = None,
    submission_path: Path | None = None,
    review: TaskReview | None = None,
) -> SubmissionTask | None:
    site = _task_site(raw_task, submission)
    source_task_id = _submission_dir_task_id(source_dir)
    task_id = (
        source_task_id
        if source_task_id is not None and source_task_id.startswith("2026")
        else _task_id(raw_task)
    )
    if site is None or task_id is None:
        return None

    task = copy.deepcopy(raw_task)
    if source_task_id is not None and source_task_id.startswith("2026"):
        task["task_id"] = source_task_id
    _apply_review_to_task(task, review)
    if "sites" not in task and "website" not in task:
        task["sites"] = [site]

    summary_path = _best_summary_path(source_dir, task_id)
    reward, run_status = _summary_metadata(summary_path)
    verifier_verdict = _verifier_verdict(source_dir, task_id)
    metadata = _submission_metadata(
        source_dir=source_dir,
        source_kind=source_kind,
        submission=submission,
        summary_path=summary_path,
        reward=reward,
        run_status=run_status,
        verifier_verdict=verifier_verdict,
        review=review,
    )
    task["_submission"] = metadata

    return SubmissionTask(
        site=site,
        task_id=task_id,
        task=task,
        source_dir=source_dir,
        source_kind=source_kind,
        submitted_at=_submission_timestamp(source_dir, submission),
        run_status=run_status,
        submission_status=str(submission["status"])
        if submission and submission.get("status") is not None
        else None,
        queue_status=str(submission["queue_status"])
        if submission and submission.get("queue_status") is not None
        else None,
        return_code=_safe_int(submission.get("return_code")) if submission else None,
        reward=reward,
        verifier_verdict=verifier_verdict,
        summary_path=summary_path,
        submission_path=submission_path,
    )


def _raw_tasks_from_study_pickle(source_dir: Path) -> list[dict[str, Any]]:
    study = _load_pickle(source_dir / "study.pkl.gz")
    if study is None:
        return []

    tasks: list[dict[str, Any]] = []
    for exp_args in getattr(study, "exp_args_list", None) or []:
        env_args = getattr(exp_args, "env_args", None)
        task_config = getattr(env_args, "task_config", None)
        raw_task = getattr(task_config, "raw_task", None)
        if isinstance(raw_task, dict):
            tasks.append(raw_task)
    return tasks


def _raw_task_from_exp_args(path: Path) -> dict[str, Any] | None:
    exp_args = _load_pickle(path)
    env_args = getattr(exp_args, "env_args", None)
    task_config = getattr(env_args, "task_config", None)
    raw_task = getattr(task_config, "raw_task", None)
    return raw_task if isinstance(raw_task, dict) else None


def _submission_tasks_from_dir(
    source_dir: Path,
    *,
    reviews_root: Path | None = None,
    mark_reviewed_submissions: bool = True,
) -> list[SubmissionTask]:
    submission_path = source_dir / "submission.json"
    submission = _load_json(submission_path)
    if isinstance(submission, dict) and _is_archived_submission(submission):
        return []

    review = _latest_task_review(source_dir, reviews_root)
    if _is_review_excluded(review):
        return []

    source_task_id = _submission_dir_task_id(source_dir)
    if isinstance(submission, dict) and isinstance(submission.get("task"), dict):
        submission = _mark_submission_reviewed(
            submission_path,
            submission,
            review,
            exact_task_id=source_task_id,
            write=mark_reviewed_submissions,
        )
        task = _make_submission_task(
            source_dir=source_dir,
            source_kind="submission.json",
            raw_task=submission["task"],
            submission=submission,
            submission_path=submission_path,
            review=review,
        )
        return [task] if task is not None else []

    tasks: list[SubmissionTask] = []
    for raw_task in _raw_tasks_from_study_pickle(source_dir):
        task = _make_submission_task(
            source_dir=source_dir,
            source_kind="study.pkl.gz",
            raw_task=raw_task,
            review=review,
        )
        if task is not None:
            tasks.append(task)

    if tasks:
        return tasks

    seen_exp_tasks: set[tuple[str, str]] = set()
    for exp_args_path in sorted(source_dir.rglob("exp_args.pkl")):
        raw_task = _raw_task_from_exp_args(exp_args_path)
        if raw_task is None:
            continue
        task = _make_submission_task(
            source_dir=source_dir,
            source_kind="exp_args.pkl",
            raw_task=raw_task,
            review=review,
        )
        if task is None:
            continue
        key = (task.site, task.task_id)
        if key in seen_exp_tasks:
            continue
        tasks.append(task)
        seen_exp_tasks.add(key)

    return tasks


def _is_failed_submission(task: SubmissionTask) -> bool:
    if task.verifier_verdict == "fail":
        return True
    if task.run_status == "failed":
        return True
    if task.submission_status == "failed":
        return True
    if task.queue_status == "failed":
        return True
    return task.return_code is not None and task.return_code != 0


def _is_verifier_failed_submission(task: SubmissionTask) -> bool:
    return task.verifier_verdict == "fail"


def _is_reviewed_submission(task: SubmissionTask) -> bool:
    metadata = task.task.get("_submission")
    return isinstance(metadata, dict) and metadata.get("reviewed") is True


def _task_sort_key(task: SubmissionTask) -> tuple[str, float, str]:
    try:
        mtime = task.source_dir.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (task.submitted_at or "", mtime, str(task.source_dir))


def _latest_run_timestamp(metadata: dict[str, Any]) -> str:
    for key in ("finished_at", "started_at", "queued_at", "created_at"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _submission_duplicate_key(task: SubmissionTask) -> tuple[str, str] | None:
    intent = _normalized_task_intent(task.task)
    if intent is None:
        return None
    return (task.site, intent)


def _submission_latest_run_sort_key(task: SubmissionTask) -> tuple[str, float, str, str]:
    metadata = task.task.get("_submission")
    timestamp = _latest_run_timestamp(metadata) if isinstance(metadata, dict) else ""
    try:
        mtime = task.source_dir.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (timestamp, mtime, task.task_id, str(task.source_dir))


def _deduplicate_submission_tasks(
    submission_tasks: list[SubmissionTask],
) -> tuple[list[SubmissionTask], int]:
    latest: dict[tuple[str, str], SubmissionTask] = {}
    unkeyed: list[SubmissionTask] = []

    for task in submission_tasks:
        key = _submission_duplicate_key(task)
        if key is None:
            unkeyed.append(task)
            continue

        previous = latest.get(key)
        if (
            previous is None
            or _submission_latest_run_sort_key(task)
            >= _submission_latest_run_sort_key(previous)
        ):
            latest[key] = task

    deduplicated = sorted(
        [*unkeyed, *latest.values()],
        key=lambda task: (task.site, task.task_id),
    )
    return deduplicated, len(submission_tasks) - len(deduplicated)


def collect_submission_tasks(
    results_root: Path | str | None = None,
    *,
    failed_only: bool = False,
    verifier_failed_only: bool = False,
    reviewed_only: bool = False,
    site: str | None = None,
    mark_reviewed_submissions: bool = True,
) -> list[SubmissionTask]:
    root = Path(results_root).expanduser() if results_root is not None else default_results_root()
    reviews_root = root / ".task_reviews"
    latest: dict[tuple[str, str], SubmissionTask] = {}

    for source_dir in _iter_submission_dirs(root):
        for task in _submission_tasks_from_dir(
            source_dir,
            reviews_root=reviews_root,
            mark_reviewed_submissions=mark_reviewed_submissions,
        ):
            if site is not None and task.site != site:
                continue
            if failed_only and not _is_failed_submission(task):
                continue
            if verifier_failed_only and not _is_verifier_failed_submission(task):
                continue
            if reviewed_only and not _is_reviewed_submission(task):
                continue
            key = (task.site, task.task_id)
            previous = latest.get(key)
            if previous is None or _task_sort_key(task) >= _task_sort_key(previous):
                latest[key] = task

    submission_tasks = sorted(latest.values(), key=lambda task: (task.site, task.task_id))
    return _deduplicate_submission_tasks(submission_tasks)[0]


def _raw_task_duplicate_key(task: dict[str, Any], site: str) -> tuple[str, str] | None:
    intent = _normalized_task_intent(task)
    if intent is None:
        return None
    return (site, intent)


def _raw_task_latest_run_sort_key(task: dict[str, Any]) -> tuple[str, float, str]:
    metadata = task.get("_submission")
    timestamp = _latest_run_timestamp(metadata) if isinstance(metadata, dict) else ""

    mtime = 0.0
    if isinstance(metadata, dict) and metadata.get("source_dir"):
        try:
            mtime = Path(str(metadata["source_dir"])).stat().st_mtime
        except OSError:
            mtime = 0.0

    task_id = str(task.get("task_id") or "")
    return (timestamp, mtime, task_id)


def _deduplicate_raw_tasks(
    tasks: list[dict[str, Any]],
    site: str,
) -> tuple[list[dict[str, Any]], int]:
    latest_index_by_key: dict[tuple[str, str], int] = {}

    for index, task in enumerate(tasks):
        key = _raw_task_duplicate_key(task, site)
        if key is None:
            continue

        previous_index = latest_index_by_key.get(key)
        if (
            previous_index is None
            or _raw_task_latest_run_sort_key(task)
            >= _raw_task_latest_run_sort_key(tasks[previous_index])
        ):
            latest_index_by_key[key] = index

    keep_indexes = set(latest_index_by_key.values())
    for index, task in enumerate(tasks):
        if _raw_task_duplicate_key(task, site) is None:
            keep_indexes.add(index)

    deduplicated = [task for index, task in enumerate(tasks) if index in keep_indexes]
    return deduplicated, len(tasks) - len(deduplicated)


def _load_raw_config(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = _load_json(path)
    if data is None:
        raise ValueError(f"Could not parse JSON config: {path}")
    if not isinstance(data, list):
        raise ValueError(f"Expected list in {path}, got {type(data).__name__}")
    if not all(isinstance(item, dict) for item in data):
        raise ValueError(f"Expected every item in {path} to be a JSON object")
    return data


def _write_raw_config(path: Path, tasks: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")


def _has_archived_submission_source(task: dict[str, Any]) -> bool:
    metadata = task.get("_submission")
    if not isinstance(metadata, dict):
        return False

    source_dir = metadata.get("source_dir")
    if not source_dir:
        return False

    submission = _load_json(Path(str(source_dir)) / "submission.json")
    return isinstance(submission, dict) and _is_archived_submission(submission)


def _is_agentlab_submission_task(task: dict[str, Any]) -> bool:
    metadata = task.get("_submission")
    return isinstance(metadata, dict) and metadata.get("source") == "agentlab_submission"


def _raw_submission_task_key(task: dict[str, Any], site: str) -> tuple[str, str] | None:
    if task.get("task_id") is None:
        return None
    return (site, str(task["task_id"]))


def _has_review_excluded_submission_source(task: dict[str, Any]) -> bool:
    metadata = task.get("_submission")
    if not isinstance(metadata, dict):
        return False

    review_path = metadata.get("review_path")
    if review_path:
        review = _load_json(Path(str(review_path)))
        if _is_review_excluded_payload(review):
            return True

    source_dir = metadata.get("source_dir")
    if not source_dir:
        return False

    source_path = Path(str(source_dir))
    review = _latest_task_review(source_path, source_path.parent / ".task_reviews")
    return _is_review_excluded(review)


def merge_submission_tasks(
    submission_tasks: list[SubmissionTask],
    config_dir: Path | str = CONFIG_DIR,
    *,
    replace_existing: bool = False,
    keep_only_collected: bool = False,
    keep_only_collected_sites: set[str] | None = None,
    dry_run: bool = False,
) -> MergeStats:
    config_root = Path(config_dir)
    stats = MergeStats(found=len(submission_tasks))
    tasks_by_site: dict[str, list[SubmissionTask]] = {}
    for task in submission_tasks:
        if not task.site:
            stats.skipped_no_site += 1
            continue
        tasks_by_site.setdefault(task.site, []).append(task)
    collected_keys = {(task.site, task.task_id) for task in submission_tasks}

    existing_sites = {
        path.name[: -len(".raw.json")]
        for path in config_root.glob("*.raw.json")
        if path.name.endswith(".raw.json")
    }

    for site in sorted(set(tasks_by_site) | existing_sites):
        tasks = tasks_by_site.get(site, [])
        raw_path = config_root / f"{site}.raw.json"
        existing_tasks = _load_raw_config(raw_path)
        active_existing_tasks = []
        prune_uncollected = keep_only_collected and (
            keep_only_collected_sites is None or site in keep_only_collected_sites
        )
        for task in existing_tasks:
            if _has_archived_submission_source(task):
                stats.removed_archived += 1
                continue
            if _has_review_excluded_submission_source(task):
                stats.removed_review_excluded += 1
                continue
            if prune_uncollected and _is_agentlab_submission_task(task):
                key = _raw_submission_task_key(task, site)
                if key not in collected_keys:
                    stats.removed_uncollected += 1
                    continue
            active_existing_tasks.append(task)

        changed = len(active_existing_tasks) != len(existing_tasks)
        existing_tasks = active_existing_tasks
        existing_index = {
            str(task["task_id"]): index
            for index, task in enumerate(existing_tasks)
            if task.get("task_id") is not None
        }

        for submission_task in sorted(tasks, key=lambda task: task.task_id):
            existing_position = existing_index.get(submission_task.task_id)
            if existing_position is None:
                existing_index[submission_task.task_id] = len(existing_tasks)
                existing_tasks.append(submission_task.task)
                stats.added += 1
                changed = True
            elif replace_existing:
                existing_tasks[existing_position] = submission_task.task
                stats.replaced += 1
                changed = True
            else:
                stats.skipped_existing += 1

        existing_tasks, removed_duplicates = _deduplicate_raw_tasks(existing_tasks, site)
        if removed_duplicates:
            stats.removed_duplicates += removed_duplicates
            changed = True

        if changed:
            stats.output_paths.append(raw_path)
            if not dry_run:
                _write_raw_config(raw_path, existing_tasks)

    return stats


def write_combined_raw_json(
    submission_tasks: list[SubmissionTask],
    output_path: Path | str,
    *,
    dry_run: bool = False,
) -> Path:
    path = Path(output_path)
    if not dry_run:
        _write_raw_config(path, [task.task for task in submission_tasks])
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect user-submitted WebArena-Pro tasks from AgentLab result "
            "directories and merge them into site raw.json configs."
        )
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=default_results_root(),
        help="AgentLab results root to scan. Defaults to AGENTLAB_RESULTS_DIR, /mnt/data/agentlab_results, then ~/agentlab_results.",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=CONFIG_DIR,
        help="Directory containing <site>.raw.json config files.",
    )
    parser.add_argument(
        "--site",
        default=None,
        help="Only collect submissions for this site.",
    )
    parser.add_argument(
        "--failed-only",
        action="store_true",
        help="Only collect submissions with failed run/verifier status.",
    )
    parser.add_argument(
        "--verifier-failed-only",
        action="store_true",
        help="Only collect submissions whose verifier final verdict is fail.",
    )
    parser.add_argument(
        "--reviewed-only",
        action="store_true",
        help="Only collect submissions that have review metadata.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace an existing raw task when the submitted site/task_id already exists.",
    )
    parser.add_argument(
        "--keep-only-collected",
        action="store_true",
        help="Remove existing agentlab submission tasks that are not in the collected set.",
    )
    parser.add_argument(
        "--combined-output",
        type=Path,
        default=None,
        help="Also write all collected submissions to one raw JSON array at this path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be collected without writing raw JSON files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    submission_tasks = collect_submission_tasks(
        args.results_root,
        failed_only=args.failed_only,
        verifier_failed_only=args.verifier_failed_only,
        reviewed_only=args.reviewed_only,
        site=args.site,
        mark_reviewed_submissions=not args.dry_run,
    )
    stats = merge_submission_tasks(
        submission_tasks,
        args.config_dir,
        replace_existing=args.replace_existing,
        keep_only_collected=args.keep_only_collected,
        keep_only_collected_sites={args.site} if args.site is not None else None,
        dry_run=args.dry_run,
    )

    combined_output = None
    if args.combined_output is not None:
        combined_output = write_combined_raw_json(
            submission_tasks,
            args.combined_output,
            dry_run=args.dry_run,
        )

    mode = "would update" if args.dry_run else "updated"
    print(
        f"Found {stats.found} submission task(s); "
        f"added {stats.added}, replaced {stats.replaced}, "
        f"removed archived {stats.removed_archived}, "
        f"removed review-excluded {stats.removed_review_excluded}, "
        f"removed uncollected {stats.removed_uncollected}, "
        f"removed duplicates {stats.removed_duplicates}, "
        f"skipped existing {stats.skipped_existing}."
    )
    for path in stats.output_paths:
        print(f"  {mode}: {path}")
    if combined_output is not None:
        print(f"  {mode}: {combined_output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
