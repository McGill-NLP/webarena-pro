"""Verifier worker registry re-exported from :mod:`webarena_pro_core.eval`."""

from __future__ import annotations

from webarena_pro_core.eval.registry import (
    dispatch_evaluation_step,
    dispatch_step_record,
    drain_step_verifiers,
    register_step_verifier,
    registered_step_verifiers,
    unregister_step_verifier,
)

__all__ = [
    "register_step_verifier",
    "unregister_step_verifier",
    "drain_step_verifiers",
    "registered_step_verifiers",
    "dispatch_step_record",
    "dispatch_evaluation_step",
]
