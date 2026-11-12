"""Task loading utilities."""

from pathlib import Path

import yaml

from metabase_agent.tasks.models import TaskSpec

EXAMPLES_DIR = Path(__file__).parent / "examples"


def load_task(task_id_or_path: str) -> TaskSpec:
    """Load a task from an ID or file path.

    Args:
        task_id_or_path: Either a task ID (looks in examples/) or a path to a YAML file.

    Returns:
        The loaded TaskSpec.

    Raises:
        FileNotFoundError: If the task file doesn't exist.
        ValueError: If the task file is invalid.
    """
    path = Path(task_id_or_path)

    if not path.suffix:
        path = EXAMPLES_DIR / f"{task_id_or_path}.yaml"

    if not path.exists():
        raise FileNotFoundError(f"Task file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid task file format: {path}")

    required_fields = ["id", "name", "instruction", "start_url"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Task file missing required field '{field}': {path}")

    return TaskSpec.from_dict(data)


def list_example_tasks() -> list[str]:
    """List available example task IDs."""
    if not EXAMPLES_DIR.exists():
        return []

    return [p.stem for p in EXAMPLES_DIR.glob("*.yaml")]
