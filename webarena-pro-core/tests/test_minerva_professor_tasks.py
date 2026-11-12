"""Keep task prompts and embedded evaluations aligned with synthetic instructor identities."""

import json
from pathlib import Path

import pytest

CONFIG = Path(__file__).parents[1] / "src/webarena_pro_core/config"
PROFESSOR_TASKS = {
    "138": ("121518", "Dr. Darian Quenvar"),
    "142": ("222178", "Dr. Darian Quenvar"),
    "143": ("120046", "Dr. Aven Quenvar"),
    "144": ("120046", "Dr. Aven Quenvar"),
}


@pytest.mark.parametrize("task_id", PROFESSOR_TASKS)
def test_professor_task_sources_agree(task_id):
    crn, instructor = PROFESSOR_TASKS[task_id]
    test_tasks = json.loads((CONFIG / "minerva-lite.raw.json").read_text())
    dev_tasks = json.loads((CONFIG / "splits/dev.json").read_text())["tasks"]
    tasks = test_tasks if task_id == "138" else dev_tasks
    task = next(t for t in tasks if t["task_id"] == task_id)
    tiered = task["eval"]
    other_tasks = dev_tasks if task_id == "138" else test_tasks
    assert not any(t["task_id"] == task_id for t in other_tasks)
    assert task["task_id"] == task_id
    assert "intent" not in tiered
    assert "Vetta" not in task["intent"]
    if task_id in {"143", "144"}:
        assert instructor in task["intent"]

    registration = tiered["nodes"][0]["eval_config"]
    assert crn in registration["rubric"]
    expected_rubric = f"Register {crn} CRN." if task_id in {"143", "144"} else f"Register for CRN {crn}."
    assert registration["rubric"] == expected_rubric
    strategies = registration["strategies"]
    assert crn in strategies[0]["config"]["checks"][0]["pattern"]
    assert strategies[-1]["config"]["rubric"] == registration["rubric"]
