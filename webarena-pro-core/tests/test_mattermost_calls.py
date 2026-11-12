"""Native call records, exact recipients, timing, and semantic callback gating."""
import copy
import json
from pathlib import Path
from datetime import date

import pytest
import requests

from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
from webarena_pro_core.eval.llm_judge import set_llm_judge_hook
from webarena_pro_core.eval.mattermost_calls import MattermostCallsEvaluator

CONFIG = Path(__file__).parents[1] / "src/webarena_pro_core/config/mattermost.raw.json"
TASK = next(t for t in json.loads(CONFIG.read_text()) if t["task_id"] == "109")
USERS = {"admin": "a", "emma.davis": "e", "bob.wilson": "b"}
BASE = {"caller": "admin", "recipients": ["emma.davis", "bob.wilson"]}
CALL = {"id": "call", "channel_id": "de", "user_id": "a", "type": "custom_calls",
        "delete_at": 0, "create_at": 1000, "props": {"start_at": 1000, "end_at": 31000, "participants": ["a"]}}
MESSAGE = {"id": "message", "channel_id": "de", "user_id": "a", "type": "",
           "message": "Please call me back when available.", "delete_at": 0, "create_at": 32000}


@pytest.fixture
def evidence(monkeypatch):
    data = {"channels": [{"id": "de", "type": "D"}, {"id": "db", "type": "D"}],
            "members": {"de": ["a", "e"], "db": ["a", "b"]},
            "posts": {"de": [copy.deepcopy(CALL)], "db": [{**copy.deepcopy(CALL), "id": "call-b", "channel_id": "db"}]},
            "requests": [], "judged": [], "verdict": "pass"}
    def get(self, spec, context):
        assert spec["method"] == "GET"  # No DM/group creation while evaluating.
        path = spec["url"].split("/api/v4/")[1]
        data["requests"].append(path)
        if path.startswith("users/username/"):
            payload = {"id": USERS[path.rsplit("/", 1)[1]]}
        elif path == "users/me/channels":
            payload = data["channels"]
        elif "/members?" in path:
            payload = [{"user_id": uid} for uid in data["members"][path.split("/")[1]]]
        elif "/posts?" in path:
            posts = data["posts"].get(path.split("/")[1], [])
            if "pages" in data:
                page = int(path.split("page=")[1].split("&")[0])
                posts = data["pages"].get((path.split("/")[1], page), [])
            payload = {"order": [p["id"] for p in posts], "posts": {p["id"]: p for p in posts}}
        else:
            raise AssertionError(path)
        if data.get("malformed"):
            payload = {"unexpected": True}
        response = requests.Response()
        response.status_code = data.get("status", 200)
        response._content = json.dumps(payload).encode()
        return response
    monkeypatch.setattr("webarena_pro_core.eval.backend_state.BackendStateEvaluator._send", get)
    def judge(rubric, context, model):
        data["judged"].append(rubric)
        return data["verdict"], "semantic verdict"
    set_llm_judge_hook(judge)
    yield data
    set_llm_judge_hook(None)


def context(**kwargs):
    value = EvalContext(task_config=TASK, **kwargs)
    value.task_start_time_ms = 1000
    return value


def evaluate(criterion):
    return MattermostCallsEvaluator().evaluate({**BASE, "criterion": criterion}, context())


def test_native_started_and_30_second_unanswered_end(evidence):
    assert evaluate("started").passed
    assert evaluate("unanswered_ended").passed
    assert not evidence["judged"]


@pytest.mark.parametrize("mutation", [
    {"type": ""}, {"user_id": "e"}, {"channel_id": "elsewhere"}, {"delete_at": 10},
    {"props": {"start_at": 0}}, {"props": {"start_at": True}},
])
def test_non_native_or_unrelated_posts_cannot_prove_call(evidence, mutation):
    evidence["posts"]["de"][0].update(mutation)
    assert not evaluate("started").passed
    assert not evaluate("unanswered_ended").passed


@pytest.mark.parametrize("members", [["a"], ["a", "b"], ["a", "e", "b"], ["e", "b"]])
def test_exact_dm_peer_required(evidence, members):
    evidence["members"]["de"] = members
    assert not evaluate("started").passed
    assert not evaluate("unanswered_ended").passed


@pytest.mark.parametrize("props", [
    {"start_at": 1000},  # still active
    {"start_at": 1000, "end_at": 30999, "participants": ["a"]},
    {"start_at": 1000, "end_at": 31000, "participants": ["a", "e"]},
    {"start_at": 1000, "end_at": 31000, "participants": ["a", "b"]},
    {"start_at": 1000, "end_at": 31000, "participants": []},
    {"start_at": 1000, "end_at": 31000},
    {"start_at": 1000, "end_at": "31000", "participants": ["a"]},
])
def test_ended_call_requires_duration_and_no_other_joiners(evidence, props):
    evidence["posts"]["de"][0]["props"] = props
    assert not evaluate("unanswered_ended").passed


def test_cannot_combine_duration_and_participants_from_different_calls(evidence):
    first = evidence["posts"]["de"][0]
    first["props"]["end_at"] = 2000
    other = copy.deepcopy(CALL)
    other["id"] = "other"
    other["props"]["participants"] = ["a", "e"]
    evidence["posts"]["de"].append(other)
    assert not evaluate("unanswered_ended").passed


def test_send_msg_keywords_do_not_pass_and_definitive_fail_never_calls_judge(evidence):
    evidence["posts"]["de"] = [copy.deepcopy(MESSAGE)]
    ctx = context(last_action="send_msg('Emma Bob call end leave')")
    nodes = TASK["eval"]["nodes"][:2]
    score, results = DAGEvaluator(parse_eval_dag({"operator": "AND", "nodes": nodes})).evaluate(ctx)
    assert score == 0
    assert not evidence["judged"]
    assert all("decided_by=T0:mattermost_calls" in r["reason"] for r in results.values())


def test_callback_requires_saved_message_before_semantic_judge(evidence):
    assert not evaluate("callback").passed
    assert not evidence["judged"]
    evidence["posts"]["de"].append(copy.deepcopy(MESSAGE))
    assert not evaluate("callback").passed
    assert not evidence["judged"]
    evidence["posts"]["db"].append({**MESSAGE, "id": "message-b", "channel_id": "db"})
    assert evaluate("callback").passed
    assert MESSAGE["message"] in evidence["judged"][0]
    assert "untrusted evidence" in evidence["judged"][0]


def test_callback_semantics_cannot_pass_just_by_keywords(evidence):
    evidence["posts"]["de"] = [{**MESSAGE, "message": "Do not call back. Emma and Bob should leave."}]
    evidence["posts"]["db"] = [{**MESSAGE, "id": "message-b", "channel_id": "db"}]
    evidence["verdict"] = "fail"
    assert not evaluate("callback").passed
    assert evidence["judged"]


def test_separate_saved_dms_cover_both_recipients(evidence):
    evidence["channels"] = [{"id": "de", "type": "D"}, {"id": "db", "type": "D"}]
    evidence["members"] = {"de": ["a", "e"], "db": ["a", "b"]}
    evidence["posts"] = {c: [{**MESSAGE, "id": c, "channel_id": c}] for c in ["de", "db"]}
    assert evaluate("callback").passed
    evidence["posts"]["db"] = []
    evidence["judged"].clear()
    assert not evaluate("callback").passed
    assert not evidence["judged"]


@pytest.mark.parametrize("mutation", [{"delete_at": 1}, {"user_id": "e"}, {"type": "custom_calls"}])
def test_callback_ignores_deleted_other_author_or_system_post(evidence, mutation):
    evidence["posts"]["de"] = [{**MESSAGE, **mutation}]
    assert not evaluate("callback").passed
    assert not evidence["judged"]


def test_backend_outage_is_inconclusive(evidence):
    evidence["status"] = 503
    result = evaluate("started")
    assert not result.passed and result.inconclusive


def test_task109_preserves_partial_credit_and_removes_keyword_heuristics():
    assert [(n["id"], n["depends_on"]) for n in TASK["eval"]["nodes"]] == [
        ("r1", []), ("r2", []), ("r3", [])]
    assert "browser_event" not in json.dumps(TASK["eval"])
    assert TASK["login_username"] == "admin"


def test_group_calls_cannot_substitute_for_the_two_direct_calls(evidence):
    evidence["channels"] = [{"id": "de", "type": "G"}]
    evidence["members"]["de"] = ["a", "e", "b"]
    assert not evaluate("started").passed
    assert not evaluate("unanswered_ended").passed


def test_calls_are_found_after_the_first_posts_page(evidence):
    noise = [{**MESSAGE, "id": f"noise-{i}"} for i in range(200)]
    evidence["pages"] = {("de", 0): noise, ("de", 1): [CALL],
                         ("db", 0): evidence["posts"]["db"]}
    assert evaluate("unanswered_ended").passed
    assert "channels/de/posts?page=1&per_page=200" in evidence["requests"]


def test_malformed_response_is_inconclusive(evidence):
    evidence["malformed"] = True
    result = evaluate("started")
    assert not result.passed and result.inconclusive


def test_dag_falls_back_on_outage_only(evidence):
    evidence["status"] = 503
    node = TASK["eval"]["nodes"][0]
    score, results = DAGEvaluator(parse_eval_dag({"operator": "AND", "nodes": [node]})).evaluate(context())
    assert score == 1
    assert evidence["judged"]
    assert "decided_by=T2:llm_judge" in results["r1"]["reason"]
    assert "INCONCLUSIVE" in results["r1"]["reason"]


def test_old_perfect_callback_messages_do_not_reach_judge(evidence):
    evidence["posts"] = {c: [{**MESSAGE, "id": c, "channel_id": c, "create_at": 1}] for c in ["de", "db"]}
    result = evaluate("callback")
    assert not result.passed and not result.inconclusive
    assert not evidence["judged"]


def test_old_native_call_does_not_satisfy_current_execution(evidence):
    evidence["posts"]["de"][0]["create_at"] = 999
    assert not evaluate("started").passed


@pytest.mark.parametrize("value", [None, "1000", True])
def test_missing_or_malformed_post_timestamp_is_inconclusive(evidence, value):
    evidence["posts"]["de"][0]["create_at"] = value
    result = evaluate("started")
    assert not result.passed and result.inconclusive


def test_legacy_date_is_a_conservative_utc_day_boundary(evidence):
    ctx = EvalContext(task_config=TASK, task_start_date=date(1970, 1, 2))
    assert not MattermostCallsEvaluator().evaluate({**BASE, "criterion": "started"}, ctx).passed
    ctx.task_start_date = "1970-01-01"
    assert MattermostCallsEvaluator().evaluate({**BASE, "criterion": "started"}, ctx).passed


def test_missing_execution_anchor_is_inconclusive(evidence):
    result = MattermostCallsEvaluator().evaluate({**BASE, "criterion": "started"}, EvalContext(task_config=TASK))
    assert not result.passed and result.inconclusive


def test_judge_evidence_preserves_creation_timestamps(evidence):
    evidence["posts"] = {c: [{**MESSAGE, "id": c, "channel_id": c}] for c in ["de", "db"]}
    assert evaluate("callback").passed
    assert '"create_at": 32000' in evidence["judged"][0]


def test_null_participants_do_not_mean_an_unanswered_call(evidence):
    for posts in evidence["posts"].values():
        posts[0]["props"]["participants"] = None
    result = evaluate("unanswered_ended")
    assert not result.passed and result.inconclusive
    node = TASK["eval"]["nodes"][1]
    score, results = DAGEvaluator(parse_eval_dag({"operator": "AND", "nodes": [node]})).evaluate(context())
    assert score == 1
    assert "decided_by=T2:llm_judge" in results["r2"]["reason"]


def test_unknown_participants_cannot_override_a_too_short_other_call(evidence):
    evidence["posts"]["de"][0]["props"]["participants"] = None
    evidence["posts"]["db"][0]["props"]["end_at"] = 2000
    result = evaluate("unanswered_ended")
    assert not result.passed and not result.inconclusive
