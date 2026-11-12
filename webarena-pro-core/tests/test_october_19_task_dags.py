"""Routing and split coverage for the eighteen October 19 approved tasks."""
import json
from pathlib import Path

import pytest
import requests

from webarena_pro_core.website_metadata import deployed_website_url
from webarena_pro_core.eval import llm_judge
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
from webarena_pro_core.splits import task_ids_for_split
from webarena_pro_core.task import WebArenaProTaskConfig

CONFIG = Path(__file__).parents[1] / "src/webarena_pro_core/config"
RAW = [t for p in CONFIG.glob("*.raw.json") for t in json.loads(p.read_text())]
DAGS = {task["task_id"]: task["eval"] for task in RAW}
TASKS = {t["task_id"]: t for t in RAW if 403 <= int(t["task_id"]) <= 420}


def test_new_approvals_are_unique_test_tasks_with_complete_rubrics():
    assert set(TASKS) == {str(i) for i in range(403, 421)}
    assert set(TASKS) <= task_ids_for_split("test")
    assert not set(TASKS) & task_ids_for_split("dev")
    assert sum(len(DAGS[task_id]["nodes"]) for task_id in TASKS) == 77
    for task in TASKS.values():
        dag = DAGS[task["task_id"]]
        assert "intent" not in dag
        assert dag["operator"] == "AND" and dag["scoring"] == "partial"
        assert len(DAGEvaluator(parse_eval_dag(dag))._topological_sort()) == len(dag["nodes"])
        assert all(n["eval_config"]["rubric"].strip() for n in dag["nodes"])


def test_task_setup_opens_the_requested_site_and_uses_the_application_role():
    calendar = TASKS["409"]
    assert calendar["sites"] == ["mattermost", "nextcloud"]
    assert calendar["login_usernames"] == {"mattermost": "admin", "nextcloud": "maya.patel"}
    assert calendar["login_username"] == "admin"
    config = WebArenaProTaskConfig.from_raw_task(calendar, container_name="calendar-task")
    assert config.start_url == deployed_website_url("mattermost")
    assert TASKS["415"]["login_usernames"]["jobportal"] == "alice_seeker"
    # Advertising one's own posting still uses the employer account.
    assert TASKS["405"]["login_usernames"]["jobportal"] == "employer_acme"


def run_scripted_judges(monkeypatch, compact_id, rejected):
    dag = DAGS[compact_id]
    ids = {n["eval_config"]["strategies"][-1]["config"]["rubric"]: n["id"] for n in dag["nodes"]}
    seen = set()
    context = EvalContext(last_action="send_msg_to_user('All requested work is complete')")

    def judge(rubric, actual_context, model):
        assert actual_context is context
        node = ids[rubric]
        seen.add(node)
        return ("fail" if node in rejected else "pass"), "scripted task-specific evidence"

    def unexpected_request(*args, **kwargs):
        pytest.fail("Presence-only backend data cannot establish this task's outcomes")

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    monkeypatch.setattr(requests, "request", unexpected_request)
    score, results = DAGEvaluator(parse_eval_dag(dag)).evaluate(context)
    return score, results, seen


@pytest.mark.parametrize("compact_id", sorted(TASKS))
def test_all_current_rubrics_reach_the_contextual_judge(monkeypatch, compact_id):
    score, results, seen = run_scripted_judges(monkeypatch, compact_id, set())
    assert score == 1
    assert len(seen) == len(results) == len(DAGS[compact_id]["nodes"])


@pytest.mark.parametrize("compact_id,rejected,expected_seen,expected_score", [
    ("419", {"r1"}, {"r1"}, 0),
    ("419", {"r2"}, {"r1", "r2", "r3", "r4", "r5"}, 4 / 5),
    ("419", {"r5"}, {"r1", "r2", "r3", "r4", "r5"}, 4 / 5),
    ("420", {"r1"}, {"r1", "r2", "r3", "r5", "r6"}, 4 / 6),
    ("420", {"r2"}, {"r1", "r2", "r3", "r4", "r6"}, 4 / 6),
    ("420", {"r3"}, {"r1", "r2", "r3", "r4", "r5"}, 4 / 6),
    ("420", {"r4", "r5", "r6"}, {"r1", "r2", "r3", "r4", "r5", "r6"}, 3 / 6),
    ("405", {"r2"}, {"r2"}, 0),
    ("406", {"r1"}, {"r1"}, 0),
    ("407", {"r1"}, {"r1"}, 0),
    ("412", {"r1"}, {"r1", "r2", "r3", "r5", "r6", "r7"}, 5 / 12),
    ("412", {"r2"}, {"r1", "r2", "r4", "r9", "r10", "r11", "r12"}, 6 / 12),
    ("413", {"r6"}, {"r1", "r2", "r3", "r4", "r5", "r6"}, 5 / 7),
    ("413", {"r3"}, {"r1", "r2", "r3", "r4", "r5", "r6"}, 5 / 7),
    ("415", {"r1"}, {"r1", "r2", "r4"}, 2 / 5),
    ("415", {"r2"}, {"r1", "r2", "r3"}, 2 / 5),
    ("417", {"r2"}, {"r2"}, 0),
    ("418", {"r1"}, {"r1"}, 0),
    ("418", {"r2"}, {"r1", "r2"}, 1 / 5),
    ("418", {"r3"}, {"r1", "r2", "r3"}, 2 / 5),
    ("418", {"r4"}, {"r1", "r2", "r3", "r4"}, 3 / 5),
])
def test_missing_prerequisites_block_only_dependent_outcomes(monkeypatch, compact_id, rejected, expected_seen, expected_score):
    score, _, seen = run_scripted_judges(monkeypatch, compact_id, rejected)
    assert score == pytest.approx(expected_score)
    assert seen == expected_seen


@pytest.mark.parametrize("compact_id,count", [("409", 6), ("411", 9)])
def test_calendar_events_and_moved_files_receive_independent_partial_credit(monkeypatch, compact_id, count):
    rejected = {f"r{i}" for i in range(2, count + 1)}
    score, results, seen = run_scripted_judges(monkeypatch, compact_id, rejected)
    assert score == pytest.approx(1 / count)
    assert len(seen) == len(results) == count
    assert {key for key, value in results.items() if value["passed"]} == {"r1"}
