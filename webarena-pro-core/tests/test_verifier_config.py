from webarena_pro_core.verifier.config import rubric_descriptions_from_task


def test_rubric_descriptions_prefer_explicit_rubrics():
    raw_task = {
        "intent": "Do the task",
        "eval": {
            "eval_types": ["rubric_verifier"],
            "reference_answers": {"hint": "Fallback hint"},
            "rubrics": [
                {"text": "Opened the right record", "type": "action"},
                "Reported the correct value",
            ],
        },
    }

    assert rubric_descriptions_from_task(raw_task) == [
        "[action] Opened the right record",
        "Reported the correct value",
    ]


def test_rubric_descriptions_fall_back_to_hint_when_no_rubrics():
    raw_task = {
        "intent": "Book the cheapest place.",
        "eval": {
            "eval_types": ["rubric_verifier"],
            "reference_answers": {"hint": "Find the cheapest listing and reserve it."},
        },
    }

    assert rubric_descriptions_from_task(raw_task) == [
        "Task intent: Book the cheapest place.\n"
        "Evaluation hint: Find the cheapest listing and reserve it."
    ]


def test_rubric_descriptions_ignore_non_rubric_verifier_tasks():
    raw_task = {
        "intent": "Answer exactly.",
        "eval": {
            "eval_types": ["string_match"],
            "rubrics": ["Should not be used"],
        },
    }

    assert rubric_descriptions_from_task(raw_task) == []
