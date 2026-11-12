"""Task selection for the active dev/test benchmark partition."""

from pathlib import Path
from typing import Any

from .task import load_raw_tasks


CONFIG_DIR = Path(__file__).parent / "config"


def load_split_tasks(split: str, config_dir: Path | str = CONFIG_DIR) -> list[dict[str, Any]]:
    """Load Dev from its bundle, or Test directly from the per-site configs."""
    if split not in {"dev", "test"}:
        raise ValueError(f"Unknown task split: {split}")
    root = Path(config_dir)
    if split == "test":
        return [
            task for path in sorted(root.glob("*.raw.json"))
            for task in load_raw_tasks(path)
        ]
    dev = load_raw_tasks(root / "splits/dev.json")
    dev_ids = {str(task["task_id"]) for task in dev}
    if not dev or len(dev_ids) != len(dev):
        raise ValueError("Dev split must be nonempty with unique task IDs")
    for task in dev:
        if not task.get("intent") or not task.get("eval", {}).get("nodes"):
            raise ValueError(f"Dev task {task['task_id']} must have an intent and a tiered DAG")
    return dev


def task_ids_for_split(split: str, config_dir: Path | str = CONFIG_DIR) -> set[str]:
    """Return compact IDs from the selected Dev or Test task definitions."""
    return {str(task["task_id"]) for task in load_split_tasks(split, config_dir)}
