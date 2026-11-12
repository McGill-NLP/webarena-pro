"""Step trace models for recording execution history."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from metabase_agent.agent.models import AgentAction


@dataclass
class StepTrace:
    """Record of a single step in task execution."""

    step: int
    action: "AgentAction"
    observation_summary: str
    url: str
    screenshot_path: Path | None = None
    reward: float = 0.0
    done: bool = False
    elapsed_ms: int = 0
    error: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "step": self.step,
            "action": self.action.to_dict() if self.action else None,
            "observation_summary": self.observation_summary,
            "url": self.url,
            "screenshot_path": str(self.screenshot_path) if self.screenshot_path else None,
            "reward": self.reward,
            "done": self.done,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class RunTrace:
    """Complete trace of a task run."""

    task_id: str
    task_name: str
    start_time: datetime
    end_time: datetime | None = None
    steps: list[StepTrace] = field(default_factory=list)
    success: bool = False
    error: str | None = None
    total_steps: int = 0
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "steps": [s.to_dict() for s in self.steps],
            "success": self.success,
            "error": self.error,
            "total_steps": self.total_steps,
            "elapsed_seconds": self.elapsed_seconds,
        }
