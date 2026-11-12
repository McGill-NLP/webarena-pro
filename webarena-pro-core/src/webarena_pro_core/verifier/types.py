"""Shared types for verifier sidecars."""

from __future__ import annotations

from webarena_pro_core.eval.protocol import (
    EvaluationStepRecord,
    StepRecord,
    StepVerifier,
    extract_first_string_arg as _extract_first_string_arg,
)

__all__ = [
    "EvaluationStepRecord",
    "StepRecord",
    "StepVerifier",
    "_extract_first_string_arg",
]
