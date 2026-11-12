from datetime import date
from types import SimpleNamespace

import pytest

from webarena_pro_core.eval.dag import EvalContext
from webarena_pro_core.eval.llm_judge import build_judge_messages


def _text(messages):
    return "\n".join(
        part["text"]
        for part in messages["regular"][1]["content"]
        if part["type"] == "text"
    )


@pytest.mark.parametrize("step_type", [dict, SimpleNamespace])
def test_current_observation_takes_precedence_over_pending_trajectory(step_type):
    context = EvalContext(
        trajectory=[
            step_type(obs={"axtree_txt": "BEFORE"}, action="click('save')"),
            step_type(obs=None),
        ],
        last_step_output={"obs": {"axtree_txt": "AFTER"}},
    )
    text = _text(build_judge_messages("Save the record", context))
    assert "AFTER" in text
    assert "BEFORE" not in text
    assert "click('save')" in text


@pytest.mark.parametrize("last_step_output", [None, {}, {"obs": None}])
def test_judge_falls_back_to_completed_trajectory_for_replay(last_step_output):
    context = EvalContext(
        trajectory=[{"obs": {"axtree_txt": "REPLAY"}}, {"obs": None}],
        last_step_output=last_step_output,
    )
    assert "REPLAY" in _text(build_judge_messages("Save the record", context))


def test_judge_does_not_replace_empty_current_evidence_with_stale_evidence():
    context = EvalContext(
        trajectory=[{"obs": {"axtree_txt": "STALE"}}],
        last_step_output={"obs": {}},
    )
    assert "STALE" not in _text(build_judge_messages("Save the record", context))


def test_judge_uses_current_observation_without_trajectory():
    context = EvalContext(last_step_output={"obs": {"axtree_txt": "CURRENT"}})
    messages = build_judge_messages("Save the record", context)
    assert "CURRENT" in _text(messages)
    assert "CURRENT" not in str(messages["pruned"])


@pytest.mark.parametrize("start_date", [date(2026, 10, 19), "2026-10-19"])
def test_judge_keeps_execution_date_when_grading_later(start_date):
    context = EvalContext(
        task_start_date=start_date,
        last_step_output={"obs": {"axtree_txt": "Calendar viewed on 2026-11-01"}},
    )
    messages = build_judge_messages("Schedule a meeting next Thursday", context)
    for variant in ("regular", "pruned"):
        text = str(messages[variant])
        assert "Task execution date: 2026-10-19 (Monday)" in text
        assert "not the date when grading occurs" in text
        assert "reference date in the rubric takes precedence" in text


@pytest.mark.parametrize("start_date", [None, "invalid"])
def test_judge_does_not_invent_a_missing_execution_date(start_date):
    messages = build_judge_messages("Schedule a meeting", EvalContext(task_start_date=start_date))
    assert "Task execution date:" not in _text(messages)
