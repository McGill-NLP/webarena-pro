"""Runner-neutral verifier sidecars for WebArena-Pro.

The protocol and worker registry are stdlib-only and always importable. The
multimodal ``RubricVerifier`` is lazy-loaded so importing this package does not
require the optional ``[verifier]`` dependencies until the verifier is used.
"""

from webarena_pro_core.eval.protocol import (
    EvaluationStepRecord,
    StepRecord,
    StepVerifier,
    extract_first_string_arg,
    rubric_descriptions_from_task,
    rubric_evaluation_spec_from_task,
    task_uses_rubric_verifier,
)
from webarena_pro_core.eval.registry import (
    dispatch_evaluation_step,
    dispatch_step_record,
    drain_step_verifiers,
    register_step_verifier,
    registered_step_verifiers,
    unregister_step_verifier,
)

__all__ = [
    "EvaluationStepRecord",
    "StepRecord",
    "StepVerifier",
    "extract_first_string_arg",
    "rubric_descriptions_from_task",
    "rubric_evaluation_spec_from_task",
    "task_uses_rubric_verifier",
    "register_step_verifier",
    "unregister_step_verifier",
    "drain_step_verifiers",
    "registered_step_verifiers",
    "dispatch_step_record",
    "dispatch_evaluation_step",
    "RubricVerifier",
]


def __getattr__(name: str):
    if name == "RubricVerifier":
        from webarena_pro_core.verifier.rubric_verifier import RubricVerifier

        return RubricVerifier
    raise AttributeError(f"module 'webarena_pro_core.verifier' has no attribute {name!r}")
