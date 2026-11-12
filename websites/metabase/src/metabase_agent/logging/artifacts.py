"""Artifact logging utilities for saving run outputs."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from metabase_agent.logging.traces import StepTrace

if TYPE_CHECKING:
    from metabase_agent.runner import RunResult
    from metabase_agent.tasks.models import TaskSpec

logger = logging.getLogger(__name__)


class ArtifactLogger:
    """Manages saving artifacts for a task run.

    Creates a structured output directory with:
    - task.json: The task specification
    - traces/: Step-by-step execution traces
    - screenshots/: Page screenshots at each step
    - summary.json: Final run summary
    """

    def __init__(self, artifacts_dir: Path) -> None:
        self.artifacts_dir = Path(artifacts_dir)
        self.screenshots_dir = self.artifacts_dir / "screenshots"
        self.traces_dir = self.artifacts_dir / "traces"

        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create artifact directories if they don't exist."""
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(exist_ok=True)
        self.traces_dir.mkdir(exist_ok=True)

    def save_task_spec(self, task: "TaskSpec") -> Path:
        """Save the task specification.

        Args:
            task: The task specification.

        Returns:
            Path to the saved file.
        """
        path = self.artifacts_dir / "task.json"
        with open(path, "w") as f:
            json.dump(task.to_dict(), f, indent=2)
        logger.debug(f"Saved task spec to {path}")
        return path

    def save_screenshot(
        self,
        screenshot_bytes: bytes | None,
        step: int,
        prefix: str = "",
    ) -> Path | None:
        """Save a screenshot.

        Args:
            screenshot_bytes: PNG image bytes.
            step: Step number.
            prefix: Optional prefix for the filename.

        Returns:
            Path to the saved file, or None if no screenshot.
        """
        if not screenshot_bytes:
            return None

        filename = f"{prefix}_{step:03d}.png" if prefix else f"step_{step:03d}.png"
        path = self.screenshots_dir / filename

        with open(path, "wb") as f:
            f.write(screenshot_bytes)

        logger.debug(f"Saved screenshot to {path}")
        return path

    def save_trace(self, trace: StepTrace) -> Path:
        """Save a step trace.

        Args:
            trace: The step trace to save.

        Returns:
            Path to the saved file.
        """
        path = self.traces_dir / f"step_{trace.step:03d}.json"
        with open(path, "w") as f:
            json.dump(trace.to_dict(), f, indent=2)
        logger.debug(f"Saved trace to {path}")
        return path

    def save_summary(self, result: "RunResult") -> Path:
        """Save the run summary.

        Args:
            result: The run result.

        Returns:
            Path to the saved file.
        """
        summary: dict[str, Any] = {
            "success": result.success,
            "summary": result.summary,
            "error": result.error,
            "total_steps": result.total_steps,
            "elapsed_seconds": result.elapsed_seconds,
            "artifacts_dir": str(result.artifacts_dir),
            "timestamp": datetime.now().isoformat(),
            "agent_answer": result.agent_answer,
            "prerequisites_satisfied": getattr(result, "prerequisites_satisfied", True),
            "missing_prerequisites": getattr(result, "missing_prerequisites", []),
        }

        path = self.artifacts_dir / "summary.json"
        with open(path, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Saved run summary to {path}")
        return path

    def save_html_snapshot(self, html: str, step: int) -> Path:
        """Save an HTML snapshot of the page.

        Args:
            html: HTML content.
            step: Step number.

        Returns:
            Path to the saved file.
        """
        path = self.artifacts_dir / "html" / f"step_{step:03d}.html"
        path.parent.mkdir(exist_ok=True)

        with open(path, "w") as f:
            f.write(html)

        logger.debug(f"Saved HTML snapshot to {path}")
        return path


def create_run_directory(base_dir: Path, task_id: str) -> Path:
    """Create a unique run directory for artifacts.

    Args:
        base_dir: Base artifacts directory.
        task_id: Task identifier.

    Returns:
        Path to the created run directory.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = base_dir / f"{task_id}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
