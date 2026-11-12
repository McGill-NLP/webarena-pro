import time

import pytest

from webarena_pro_core.eval import (
    dispatch_step_record,
    drain_step_verifiers,
    extract_first_string_arg,
    register_step_verifier,
    registered_step_verifiers,
    rubric_descriptions_from_task,
    rubric_evaluation_spec_from_task,
    task_uses_rubric_verifier,
    unregister_step_verifier,
    validate_rubric_step_record,
)


def _valid_record() -> dict:
    screenshot = object()
    return {
        "step": 0,
        "action": "click('submit')",
        "screenshot_before": screenshot,
        "screenshot_after": screenshot,
        "is_final_step": False,
        "timestamp": time.time(),
    }


def test_rubric_descriptions_prefer_explicit_rubrics():
    raw_task = {
        "task_id": "001",
        "intent": "Do the thing",
        "eval": {
            "eval_types": ["rubric_verifier"],
            "rubrics": [
                {"type": "action", "text": "Opened the correct page"},
                {"criterion": "Submitted the final answer"},
            ],
        },
    }

    assert task_uses_rubric_verifier(raw_task)
    assert rubric_descriptions_from_task(raw_task) == [
        "[action] Opened the correct page",
        "Submitted the final answer",
    ]
    spec = rubric_evaluation_spec_from_task(raw_task)
    assert spec is not None
    assert spec.task_id == "001"
    assert spec.rubric_descriptions == (
        "[action] Opened the correct page",
        "Submitted the final answer",
    )


def test_rubric_descriptions_fall_back_to_hint_and_ignore_other_tasks():
    assert rubric_descriptions_from_task({"eval": {"eval_types": ["dag"]}}) == []

    raw_task = {
        "intent": "Find the invoice total",
        "eval": {
            "eval_types": ["rubric_verifier"],
            "reference_answers": {"hint": "The answer should be $42."},
        },
    }

    assert rubric_descriptions_from_task(raw_task) == [
        "Task intent: Find the invoice total\nEvaluation hint: The answer should be $42."
    ]


def test_validate_rubric_step_record_requires_judge_inputs():
    validate_rubric_step_record(_valid_record())

    invalid = _valid_record()
    invalid["screenshot_after"] = None

    with pytest.raises(ValueError, match="screenshot_after"):
        validate_rubric_step_record(invalid)


def test_extract_first_string_arg_from_action():
    assert extract_first_string_arg("click('abc')") == "abc"
    assert extract_first_string_arg("send_msg_to_user(message='done')") is None
    assert extract_first_string_arg("not valid python") is None


def test_step_verifier_registry_dispatches_records():
    seen = []

    class FakeVerifier:
        def on_agent_step_end(self, record):
            seen.append(record)

    verifier = FakeVerifier()
    register_step_verifier(verifier)
    try:
        assert verifier in registered_step_verifiers()
        dispatch_step_record(_valid_record())
        drain_step_verifiers(timeout=5)
    finally:
        unregister_step_verifier(verifier)

    assert len(seen) == 1
    assert seen[0]["action"] == "click('submit')"
