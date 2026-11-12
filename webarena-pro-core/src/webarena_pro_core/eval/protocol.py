"""Runner-neutral evaluation protocol for WebArena-Pro.

This module intentionally stays stdlib-only. Experiment runners such as
BrowserGym/AgentLab or replay scripts should convert their native step
objects into these records before talking to core evaluators or judge sidecars.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Mapping, NotRequired, Protocol, TypedDict, runtime_checkable


BBox = tuple[float, float, float, float]


class EvaluationStepRecord(TypedDict):
    """One normalized agent step, suitable for rubric-style judges.

    Required fields are the minimum a multimodal rubric judge needs to reason
    about a step without knowing which runner produced it. Optional fields add
    provenance, page context, and runner-specific debugging breadcrumbs.
    """

    step: int
    action: str
    screenshot_before: Any
    screenshot_after: Any
    is_final_step: bool
    timestamp: float
    task_name: NotRequired[str | None]
    task_id: NotRequired[str | None]
    exp_dir: NotRequired[str | None]
    goal: NotRequired[str | None]
    url: NotRequired[str | None]
    final_answer: NotRequired[str | None]
    bid: NotRequired[str | None]
    bbox: NotRequired[BBox | None]
    agent_think: NotRequired[str | None]
    runner_name: NotRequired[str | None]
    runner_metadata: NotRequired[dict[str, Any]]


# Backwards-friendly alias for existing verifier implementations.
StepRecord = EvaluationStepRecord


@runtime_checkable
class StepVerifier(Protocol):
    """Observer callback implemented by judge/verifier sidecars."""

    def on_agent_step_end(self, record: EvaluationStepRecord) -> None: ...


class EvaluationStepConverter(Protocol):
    """Adapter implemented by experiment runners.

    A converter owns framework-specific extraction: screenshots, target bboxes,
    final-action detection, result directories, and any agent-thought fields.
    The evaluation framework only consumes the normalized record it returns.
    """

    def to_evaluation_step_record(self) -> EvaluationStepRecord: ...


@dataclass(frozen=True)
class RubricEvaluationSpec:
    """Rubric verifier configuration extracted from a raw task."""

    task_id: str | None
    intent: str | None
    eval_config: Mapping[str, Any]
    rubric_descriptions: tuple[str, ...]


RUBRIC_VERIFIER_EVAL_TYPE = "rubric_verifier"
RUBRIC_REQUIRED_STEP_FIELDS = (
    "step",
    "action",
    "screenshot_before",
    "screenshot_after",
    "is_final_step",
    "timestamp",
)


def task_uses_rubric_verifier(raw_task: Mapping[str, Any] | None) -> bool:
    """Return whether a raw task requests the rubric verifier."""

    if not isinstance(raw_task, Mapping):
        return False

    eval_cfg = raw_task.get("eval", raw_task.get("evaluation"))
    if not isinstance(eval_cfg, Mapping):
        return False

    eval_types = eval_cfg.get("eval_types") or []
    return isinstance(eval_types, list) and RUBRIC_VERIFIER_EVAL_TYPE in eval_types


def rubric_descriptions_from_task(raw_task: Mapping[str, Any] | None) -> list[str]:
    """Return rubric descriptions for a raw task.

    Preference order:
    1. Explicit ``eval.rubrics`` entries.
    2. ``eval.reference_answers.hint``.
    3. ``eval.string_note`` or top-level ``hint``.
    4. The task intent as a last-resort criterion.
    """

    if not task_uses_rubric_verifier(raw_task):
        return []

    assert raw_task is not None
    eval_cfg = raw_task.get("eval", raw_task.get("evaluation"))
    assert isinstance(eval_cfg, Mapping)

    descriptions: list[str] = []
    rubrics = eval_cfg.get("rubrics", raw_task.get("rubrics"))
    if isinstance(rubrics, list):
        for rubric in rubrics:
            if isinstance(rubric, str):
                text = _string_value(rubric)
                if text:
                    descriptions.append(text)
                continue

            if isinstance(rubric, Mapping):
                text = (
                    _string_value(rubric.get("text"))
                    or _string_value(rubric.get("description"))
                    or _string_value(rubric.get("criterion"))
                )
                if not text:
                    continue
                rubric_type = _string_value(rubric.get("type"))
                descriptions.append(f"[{rubric_type}] {text}" if rubric_type else text)

    if descriptions:
        return descriptions

    reference_answers = eval_cfg.get("reference_answers")
    hint = None
    if isinstance(reference_answers, Mapping):
        hint = _string_value(reference_answers.get("hint"))
    hint = (
        hint
        or _string_value(eval_cfg.get("string_note"))
        or _string_value(raw_task.get("hint"))
    )
    if hint:
        intent = _string_value(raw_task.get("intent"))
        if intent:
            return [f"Task intent: {intent}\nEvaluation hint: {hint}"]
        return [hint]

    intent = _string_value(raw_task.get("intent"))
    return [f"Task intent: {intent}"] if intent else []


def rubric_evaluation_spec_from_task(
    raw_task: Mapping[str, Any] | None,
) -> RubricEvaluationSpec | None:
    """Extract a runner-neutral rubric spec from a raw task config."""

    descriptions = rubric_descriptions_from_task(raw_task)
    if not descriptions or raw_task is None:
        return None

    eval_cfg = raw_task.get("eval", raw_task.get("evaluation"))
    if not isinstance(eval_cfg, Mapping):
        return None

    task_id_value = raw_task.get("task_id")
    intent_value = raw_task.get("intent")
    return RubricEvaluationSpec(
        task_id=str(task_id_value) if task_id_value is not None else None,
        intent=str(intent_value) if intent_value is not None else None,
        eval_config=eval_cfg,
        rubric_descriptions=tuple(descriptions),
    )


def validate_rubric_step_record(record: Mapping[str, Any]) -> None:
    """Validate the runtime fields required by rubric verifier judges.

    The type contract above helps static checkers; this function gives runner
    adapters a precise runtime failure when their converter omits data the judge
    needs.
    """

    missing = [
        field
        for field in RUBRIC_REQUIRED_STEP_FIELDS
        if field not in record or record.get(field) is None
    ]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(
            "Evaluation step record is missing rubric verifier field(s): "
            f"{joined}"
        )

    if not isinstance(record.get("step"), int):
        raise TypeError("Evaluation step record field `step` must be an int.")
    if not isinstance(record.get("action"), str):
        raise TypeError("Evaluation step record field `action` must be a str.")
    if not isinstance(record.get("is_final_step"), bool):
        raise TypeError(
            "Evaluation step record field `is_final_step` must be a bool."
        )
    if not isinstance(record.get("timestamp"), (int, float)):
        raise TypeError("Evaluation step record field `timestamp` must be numeric.")


def extract_first_string_arg(action: str) -> str | None:
    """Return the first string positional arg from the first call in ``action``."""

    try:
        tree = ast.parse(action)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if not node.args:
                return None
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                return first.value
            return None
    return None


def _string_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None
