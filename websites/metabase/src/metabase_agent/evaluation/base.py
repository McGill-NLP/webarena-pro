"""Base evaluation interfaces."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from metabase_agent.agent.models import Observation
    from metabase_agent.logging.traces import StepTrace
    from metabase_agent.tasks.models import TaskSpec


@dataclass
class EvaluationResult:
    """Result of evaluating a task's success."""

    success: bool
    reason: str
    score: float = 0.0
    details: dict | None = None

    @classmethod
    def passed(cls, reason: str, score: float = 1.0) -> "EvaluationResult":
        """Create a successful evaluation result."""
        return cls(success=True, reason=reason, score=score)

    @classmethod
    def failed(cls, reason: str, score: float = 0.0) -> "EvaluationResult":
        """Create a failed evaluation result."""
        return cls(success=False, reason=reason, score=score)


class Evaluator(Protocol):
    """Protocol for task evaluators.

    Evaluators check whether a task has been completed successfully
    based on the task specification, execution history, and final state.
    """

    def evaluate(
        self,
        task: "TaskSpec",
        traces: list["StepTrace"],
        final_observation: "Observation",
    ) -> EvaluationResult:
        """Evaluate whether the task was completed successfully.

        Args:
            task: The task specification with success criteria.
            traces: History of steps taken during execution.
            final_observation: The final browser state.

        Returns:
            EvaluationResult indicating success/failure and reasoning.
        """
        ...
