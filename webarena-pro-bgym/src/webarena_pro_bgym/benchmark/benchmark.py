import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from browsergym.core.action.highlevel import HighLevelActionSet
from browsergym.experiments.benchmark.base import HighLevelActionSetArgs
from browsergym.experiments.benchmark.configs import DEFAULT_HIGHLEVEL_ACTION_SET_ARGS

from agentlab.benchmarks.abstract_env import AbstractBenchmark

from webarena_pro_core.task import CONFIG_DIR as CORE_CONFIG_DIR
from webarena_pro_core.task import load_task_configs

from .env import WebArenaProEnvArgs, extract_frames, listen, transcribe, watch


logger = logging.getLogger(__name__)

_CONFIG_DIR = CORE_CONFIG_DIR


class WebArenaProActionSet(HighLevelActionSet):
    """Carry per-agent video limits into BrowserGym's generated action code."""

    def to_python_code(self, action: str) -> str:
        code = super().to_python_code(action)
        return (
            "from webarena_pro_bgym.benchmark.env import _WATCH_SETTINGS\n"
            f"_WATCH_SETTINGS.set(({self.watch_audio_support!r}, {self.watch_token_budget!r}))\n"
            + code
        )


@dataclass
class WebArenaProActionSetArgs(HighLevelActionSetArgs):
    """Action set args for WebArena-Pro. Defaults combine `webarena` and
    `coord` actions with `transcribe(url, start_seconds, end_seconds)` and
    `extract_frames(url, n_frames, start_seconds, end_seconds)` actions.
    Audio/video-capable agents opt in to `listen()`/`watch()` separately."""

    audio_support: bool = False
    vision_support: bool = True
    video_support: bool = False
    watch_token_budget: int = 131_072

    def make_action_set(self) -> HighLevelActionSet:
        custom_actions = [transcribe]
        if self.vision_support:
            custom_actions.append(extract_frames)
        if self.audio_support:
            custom_actions.append(listen)
        if self.video_support:
            custom_actions.append(watch)
        actions = WebArenaProActionSet(
            subsets=self.subsets,
            custom_actions=custom_actions,
            multiaction=self.multiaction,
            strict=self.strict,
            retry_with_force=self.retry_with_force,
            demo_mode=self.demo_mode,
        )
        actions.watch_audio_support = self.audio_support
        actions.watch_token_budget = self.watch_token_budget
        return actions


_DEFAULT_WEBARENA_PRO_ACTION_SET_ARGS = WebArenaProActionSetArgs(
    subsets=("webarena", "coord", "custom"),
    multiaction=DEFAULT_HIGHLEVEL_ACTION_SET_ARGS["webarena"].multiaction,
    strict=DEFAULT_HIGHLEVEL_ACTION_SET_ARGS["webarena"].strict,
    retry_with_force=DEFAULT_HIGHLEVEL_ACTION_SET_ARGS["webarena"].retry_with_force,
    demo_mode=DEFAULT_HIGHLEVEL_ACTION_SET_ARGS["webarena"].demo_mode,
)


class WebArenaProBenchmark(AbstractBenchmark):
    name: str = "webarena-pro-bgym"
    is_multi_tab: bool = True
    high_level_action_set_args: HighLevelActionSetArgs = _DEFAULT_WEBARENA_PRO_ACTION_SET_ARGS
    env_args_list: list["WebArenaProEnvArgs"] = None  # type: ignore
    task_dependencies: dict[str, list[str]] = None  # type: ignore
    use_task_dependencies: bool = False

    # Pass a list of site names (e.g. ["nextcloud", "metabase"]) or "all" to load every site.
    sites: Union[list[str], str] = "all"
    split: str | None = None
    config_dir: Path | None = None

    def __post_init__(self):
        self._load_tasks()

    def model_post_init(self, context):
        """Load the selected split and create self.env_args_list."""
        self._load_tasks()

    def _load_tasks(self) -> None:
        self.env_args_list = []
        self.task_dependencies = {}
        previous_task_by_website: dict[str, str] = {}
        config_dir = self.config_dir or _CONFIG_DIR
        for task_config in load_task_configs(self.sites, config_dir=config_dir, split=self.split):
            task_name = f"{self.name}.{task_config.task_id}"
            env_args = WebArenaProEnvArgs(task_config=task_config, task_name=task_name)
            self.env_args_list.append(env_args)

            if self.use_task_dependencies:
                previous_task_name = previous_task_by_website.get(task_config.website)
                self.task_dependencies[task_name] = [previous_task_name] if previous_task_name else []
                previous_task_by_website[task_config.website] = task_name
            else:
                self.task_dependencies[task_name] = []

        logger.info("Loaded %s tasks from %s (split=%s)", len(self.env_args_list), config_dir, self.split)

    def dependency_graph_over_tasks(self) -> dict[str, list[str]]:
        return dict(self.task_dependencies)
