"""BrowserGym-free task configuration helpers for WebArena-Pro."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .website_metadata import (
    deployed_website_login_url,
    deployed_website_login_urls,
    deployed_website_url,
    deployed_website_urls,
)

CONFIG_DIR = Path(__file__).parent / "config"

DEPLOYED_WEBSITE_URLS = deployed_website_urls()
DEPLOYED_WEBSITE_LOGIN_URLS = deployed_website_login_urls()


@dataclass
class WebArenaProTaskConfig:
    task_id: str
    intent: str
    sites: tuple[str, ...]
    container_name: str
    start_url: str
    evaluation: dict[str, Any] | None = None
    require_login: bool = False
    login_page: str | None = None
    login_username: str | None = None
    login_usernames: dict[str, str] | None = None
    startup_wait_seconds: float = 0.0
    raw_task: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.sites = tuple(dict.fromkeys(self.sites))
        if not self.sites:
            raise ValueError("Task config `sites` must contain at least one website.")
        if self.login_usernames is None:
            self.login_usernames = {}
        if self.login_username is not None and self.website not in self.login_usernames:
            self.login_usernames[self.website] = self.login_username

    @property
    def website(self) -> str:
        return self.sites[0]

    @classmethod
    def from_raw_task(
        cls,
        raw_task: dict[str, Any],
        container_name: str,
    ) -> "WebArenaProTaskConfig":
        legacy_website_value = raw_task.get("website")
        raw_sites = raw_task.get("sites")
        sites: list[str] = []
        if isinstance(raw_sites, list) and raw_sites:
            sites = [str(site) for site in raw_sites]
            if (
                legacy_website_value is not None
                and str(legacy_website_value) != sites[0]
            ):
                raise ValueError(
                    "`website` is a legacy alias and must match the first "
                    "entry in `sites` when both are provided."
                )
        elif legacy_website_value is not None:
            sites = [str(legacy_website_value)]

        if not sites:
            raise ValueError(
                "Task is missing website information. Expected non-empty `sites`."
            )

        start_site = sites[0]
        unknown_sites = [site for site in sites if site not in DEPLOYED_WEBSITE_URLS]
        if unknown_sites:
            raise ValueError(
                f"No deployed URL configured for website(s) {unknown_sites}. "
                "Update webarena_pro_core.task.DEPLOYED_WEBSITE_URLS."
            )
        start_url = _resolve_deployed_url(start_site)

        startup_wait_seconds = float(raw_task.get("startup_wait_seconds", 0.0))
        if startup_wait_seconds < 0:
            startup_wait_seconds = 0.0

        require_login = bool(raw_task.get("require_login", False))
        login_page = _resolve_deployed_login_url(start_site)
        login_usernames = _parse_login_usernames(raw_task, primary_site=start_site)
        unknown_login_sites = sorted(set(login_usernames) - set(sites))
        if unknown_login_sites:
            raise ValueError(
                "`login_usernames` contains site(s) not listed in `sites`: "
                f"{unknown_login_sites}"
            )
        login_username_value = raw_task.get("login_username", None)
        login_username = (
            str(login_username_value)
            if login_username_value is not None
            else login_usernames.get(start_site)
        )

        evaluation = raw_task.get("eval", raw_task.get("evaluation"))
        if not isinstance(evaluation, dict):
            evaluation = None

        return cls(
            task_id=str(raw_task["task_id"]),
            intent=str(raw_task["intent"]),
            sites=tuple(dict.fromkeys(sites)),
            evaluation=evaluation,
            container_name=container_name,
            start_url=start_url,
            require_login=require_login,
            login_page=login_page,
            login_username=login_username,
            login_usernames=login_usernames,
            startup_wait_seconds=startup_wait_seconds,
            raw_task=dict(raw_task),
        )


def _parse_login_usernames(
    raw_task: dict[str, Any],
    *,
    primary_site: str,
) -> dict[str, str]:
    """Parse per-site login username selections from task JSON."""
    login_usernames: dict[str, str] = {}
    raw_login_usernames = raw_task.get("login_usernames")
    if raw_login_usernames is not None:
        if not isinstance(raw_login_usernames, dict):
            raise ValueError("`login_usernames` must be an object mapping site to username.")
        login_usernames.update(
            {
                str(site): str(username)
                for site, username in raw_login_usernames.items()
                if username is not None
            }
        )

    legacy_username = raw_task.get("login_username")
    if legacy_username is not None and primary_site not in login_usernames:
        login_usernames[primary_site] = str(legacy_username)

    return login_usernames


def _resolve_deployed_url(site: str) -> str:
    try:
        return deployed_website_url(site)
    except KeyError:
        return DEPLOYED_WEBSITE_URLS[site]


def _resolve_deployed_login_url(site: str) -> str | None:
    try:
        return deployed_website_login_url(site)
    except KeyError:
        return DEPLOYED_WEBSITE_LOGIN_URLS.get(site)


def task_config_files(
    sites: Sequence[str] | str = "all",
    *,
    config_dir: Path | str | None = None,
) -> list[Path]:
    """Return raw task config files for the requested site selection."""
    root = Path(config_dir) if config_dir is not None else CONFIG_DIR
    if sites == "all":
        return sorted(root.glob("*.raw.json"))
    site_names = [sites] if isinstance(sites, str) else list(sites)
    return [root / f"{site}.raw.json" for site in site_names]


def load_raw_tasks(config_file: Path | str) -> list[dict[str, Any]]:
    """Load task records, including their embedded evaluation DAGs.

    Accept a task array or a bundle with a ``tasks`` array and metadata such
    as ``sampling``. Metadata is not passed to task configuration consumers.

    Older external configs may still provide an adjacent ``*.tiered.json``
    sidecar. It supplies evaluations only for tasks without an embedded DAG.
    """
    path = Path(config_file)
    if path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8") as handle:
        raw_tasks = json.load(handle)

    if isinstance(raw_tasks, dict) and "tasks" in raw_tasks:
        raw_tasks = raw_tasks["tasks"]

    if not isinstance(raw_tasks, list):
        raise ValueError(
            f"Expected list of task objects in {path}, got {type(raw_tasks).__name__}."
        )

    for index, raw_task in enumerate(raw_tasks):
        if not isinstance(raw_task, dict):
            raise ValueError(
                f"Task at index {index} in {path} is not an object/dict."
            )
    _apply_tiered_evaluations(raw_tasks, path)
    return raw_tasks


def _apply_tiered_evaluations(
    raw_tasks: list[dict[str, Any]],
    raw_path: Path,
) -> None:
    legacy_tasks = []
    for task in raw_tasks:
        evaluation = task.get("eval", task.get("evaluation"))
        if not isinstance(evaluation, dict) or not isinstance(evaluation.get("nodes"), list):
            legacy_tasks.append(task)
    if not legacy_tasks:
        return

    if raw_path.name.endswith(".raw.json"):
        tiered_path = raw_path.with_name(
            f"{raw_path.name.removesuffix('.raw.json')}.tiered.json"
        )
    elif raw_path.name == "dev.json":
        tiered_path = raw_path.with_name("dev.tiered.json")
    else:
        return
    if not tiered_path.exists() or tiered_path.stat().st_size == 0:
        return

    with tiered_path.open("r", encoding="utf-8") as handle:
        tiered_payload = json.load(handle)
    if not isinstance(tiered_payload, dict):
        raise ValueError(
            f"Expected object mapping task ids to DAGs in {tiered_path}, "
            f"got {type(tiered_payload).__name__}."
        )

    tiered_by_id: dict[str, dict[str, Any]] = {}
    tiered_by_intent: dict[str, dict[str, Any]] = {}
    for task_id, evaluation in tiered_payload.items():
        if str(task_id).startswith("_"):
            continue
        if not isinstance(evaluation, dict):
            raise ValueError(
                f"Tiered evaluation {task_id!r} in {tiered_path} is not an object."
            )
        tiered_by_id[str(task_id)] = evaluation
        intent = evaluation.get("intent")
        if isinstance(intent, str) and intent:
            if intent in tiered_by_intent:
                raise ValueError(
                    f"Duplicate tiered-evaluation intent in {tiered_path}: {intent!r}"
                )
            tiered_by_intent[intent] = evaluation

    for raw_task in legacy_tasks:
        evaluation = None
        for candidate in (
            raw_task.get("original_task_id"),
            raw_task.get("task_id"),
        ):
            if candidate is not None:
                evaluation = tiered_by_id.get(str(candidate))
            if evaluation is not None:
                break
        if evaluation is None:
            intent = raw_task.get("intent")
            if isinstance(intent, str):
                evaluation = tiered_by_intent.get(intent)
        if evaluation is None:
            continue

        dag = deepcopy(evaluation)
        dag.pop("intent", None)
        raw_task["eval"] = dag


def task_container_name(
    task_id: str,
    index: int,
    *,
    prefix: str = "webarena-pro",
) -> str:
    safe_task_id = str(task_id).replace("_", "-").replace(" ", "-").lower()
    return f"{prefix}-{safe_task_id}-{index}"


def load_task_configs(
    sites: Sequence[str] | str = "all",
    *,
    config_dir: Path | str | None = None,
    container_prefix: str = "webarena-pro",
    split: str | None = None,
) -> list[WebArenaProTaskConfig]:
    """Load Test from per-site files by default, or Dev from its own bundle."""
    if split is not None:
        from .splits import load_split_tasks

        raw_tasks = load_split_tasks(split, config_dir or CONFIG_DIR)
    else:
        raw_tasks = []
        for config_file in task_config_files(sites, config_dir=config_dir):
            if not config_file.exists():
                raise FileNotFoundError(f"Config file not found: {config_file}")
            raw_tasks.extend(load_raw_tasks(config_file))

    selected_sites = None if sites == "all" else {sites} if isinstance(sites, str) else set(sites)
    task_configs: list[WebArenaProTaskConfig] = []
    for global_index, raw_task in enumerate(raw_tasks):
        task_id = str(raw_task.get("task_id", f"task-{global_index}"))
        task_config = WebArenaProTaskConfig.from_raw_task(
            raw_task=raw_task,
            container_name=task_container_name(task_id, global_index, prefix=container_prefix),
        )
        if selected_sites is None or task_config.website in selected_sites:
            task_configs.append(task_config)
    return task_configs
