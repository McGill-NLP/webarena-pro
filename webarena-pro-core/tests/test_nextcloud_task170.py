"""Task 170 preserves its contact-based workflow and evaluates each criterion."""

import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import requests

from webarena_pro_core.eval import llm_judge
from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
from webarena_pro_core.task import WebArenaProTaskConfig


CONFIG = Path(__file__).parents[1] / "src/webarena_pro_core/config"
TASK = next(
    task
    for task in json.loads((CONFIG / "nextcloud.raw.json").read_text())
    if task["task_id"] == "170"
)


@pytest.mark.parametrize(
    "failed,folder_exists,score",
    [
        (set(), True, 1),
        ({"r1"}, True, 4 / 5),
        ({"r2"}, True, 4 / 5),
        ({"r4"}, True, 4 / 5),
        ({"r5"}, True, 4 / 5),
        (set(), False, 3 / 5),
    ],
)
def test_actual_dag_preserves_workflow_criteria(
    monkeypatch, failed, folder_exists, score
):
    rubrics = {
        strategy["config"]["rubric"]: node["id"]
        for node in TASK["eval"]["nodes"]
        for strategy in node["eval_config"]["strategies"]
        if strategy["type"] == "llm_judge"
    }
    judged = []

    def judge(rubric, context, model):
        node_id = rubrics[rubric]
        judged.append(node_id)
        return (
            "fail" if node_id in failed else "pass",
            "Scripted criterion result; checks DAG wiring, not LLM accuracy",
        )

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)

    def send(self, spec, context):
        path = urlsplit(self._resolve_url(spec["url"], context)).path
        response = requests.Response()
        if path == "/ocs/v2.php/apps/spreed/api/v4/room":
            # A seeded room must not bypass judging the requested participants.
            response.status_code = 200
            response._content = json.dumps(
                {"ocs": {"data": [{"displayName": "Unrelated seeded room"}]}}
            ).encode()
        else:
            assert path == "/remote.php/dav/files/maya.patel/interview"
            response.status_code = 200 if folder_exists else 404
            response._content = b""
        return response

    monkeypatch.setattr(BackendStateEvaluator, "_send", send)
    actual, _ = DAGEvaluator(parse_eval_dag(TASK["eval"])).evaluate(
        EvalContext(task_config=TASK, task_start_date=date(2026, 10, 27))
    )
    assert actual == pytest.approx(score)
    assert "r1" in judged
    assert "r3" not in judged
    assert ("r4" in judged) == folder_exists


def test_task_load_split_and_reviewed_intent_alignment():
    WebArenaProTaskConfig.from_raw_task(TASK, container_name="task170-test")
    assert sum(
        task["task_id"] == "170"
        for path in CONFIG.glob("*.raw.json")
        for task in json.loads(path.read_text())
    ) == 1
    assert not any(
        task["task_id"] == "170"
        for task in json.loads((CONFIG / "splits/dev.json").read_text())["tasks"]
    )
    nodes = {node["id"]: node["eval_config"] for node in TASK["eval"]["nodes"]}
    group_rubric = nodes["r1"]["strategies"][0]["config"]["rubric"]
    for name in ("Nancy", "Lisa", "Richard"):
        assert name in TASK["intent"]
        assert name in group_rubric
    assert "'marketing'." in TASK["intent"]
    request_rubric = nodes["r4"]["strategies"][0]["config"]["rubric"]
    assert "task execution date" in request_rubric
    assert "interview folder" in request_rubric
