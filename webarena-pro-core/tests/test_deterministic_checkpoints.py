"""Authoritative state checks; task 344 falls back only for inconclusive probes."""
import json
from pathlib import Path

import pytest
import requests

from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
from webarena_pro_core.eval import llm_judge

CONFIG = Path(__file__).parents[1] / "src/webarena_pro_core/config"
TASKS = {task["task_id"]: task for path in CONFIG.glob("*.raw.json") for task in json.loads(path.read_text())}
START = 1000
LINK = "http://yt-lite-w3.localhost:8080/watch/fv238"
RECIPES = "Blueberry Smoothie Bowl, Homemade Cereal and Chocolate PB Overnight Oats."


def response(payload, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    return result


@pytest.fixture(autouse=True)
def no_judge(monkeypatch):
    monkeypatch.setenv("WP_YT_LITE_URL", "http://yt-lite-w3.localhost:8080")
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", lambda *_: pytest.fail("Unexpected LLM fallback"))


def grade(task_id, context=None):
    task = TASKS[task_id]
    context = context or EvalContext(task_config=task, task_start_time_ms=START)
    result = DAGEvaluator(parse_eval_dag(task["eval"])).evaluate(context)
    assert context.judge_audits == []
    return result


def post(**changes):
    return {"id": "post", "user_id": "john-id", "channel_id": "watercooler-id",
            "create_at": START + 10, "delete_at": 0, "type": "", "message": RECIPES + " " + LINK,
            **changes}


@pytest.fixture
def mattermost(monkeypatch):
    state = {"posts": [post()], "status": 200, "calls": []}

    def send(_self, spec, context):
        url = spec["url"]
        state["calls"].append(url)
        assert spec["auth_user"] == "john.doe"
        if state["status"] != 200:
            return response({}, state["status"])
        if url.endswith("users/username/john.doe"):
            return response({"id": "john-id"})
        if url.endswith("teams/name/general/channels/name/watercooler"):
            return response({"id": "watercooler-id", "delete_at": state.get("channel_deleted_at", 0)})
        if "/channels/watercooler-id/posts?" in url:
            page = int(url.split("page=")[1].split("&")[0])
            rows = state["posts"][page * 200:(page + 1) * 200]
            return response({"posts": {row["id"]: row for row in rows}, "order": [row["id"] for row in rows]})
        pytest.fail(f"unexpected probe: {url}")

    monkeypatch.setattr(BackendStateEvaluator, "_send", send)
    return state


def test_112_stays_stable_then_loses_only_undone_credit(mattermost):
    ctx = EvalContext(task_config=TASKS["112"], task_start_time_ms=START)
    for step in range(4):
        ctx.trajectory.append({"action": "noop()", "obs": {"axtree_txt": str(step)}})
        score, results = grade("112", ctx)
        assert score == 1
        assert all("decided_by=T0:backend_state" in value["reason"] for value in results.values())
    mattermost["posts"][0]["message"] = RECIPES
    assert grade("112")[0] == 0.5
    mattermost["posts"][0]["message"] = LINK
    assert grade("112")[0] == 0.5
    mattermost["posts"][0]["delete_at"] = START + 50
    assert grade("112")[0] == 0
    mattermost["posts"] = []
    assert grade("112")[0] == 0
    mattermost["posts"] = [post(id="recreated")]
    assert grade("112")[0] == 1


@pytest.mark.parametrize("change", [
    {"user_id": "someone-else"}, {"channel_id": "other-channel"}, {"create_at": START - 1},
    {"delete_at": START + 1}, {"type": "custom_system"},
])
def test_112_rejects_wrong_author_channel_old_deleted_and_system_posts(mattermost, change):
    mattermost["posts"] = [post(**change)]
    assert grade("112")[0] == 0


@pytest.mark.parametrize("url", [
    "http://yt-lite-w3.localhost:8080/watch/fv239", "http://evil.example/watch/fv238",
    "http://yt-lite-w3.localhost:8080/watch/fv2380", "http://yt-lite-w3.localhost:8080/watch/fv238/extra",
    "http://yt-lite-w2.localhost:8080/watch/fv238", "http://yt-lite-w3.localhost:8080/watch?v=fv238",
])
def test_112_wrong_exact_link_is_a_final_failure(mattermost, url):
    mattermost["posts"][0]["message"] = RECIPES + " " + url
    score, results = grade("112")
    assert score == 0.5 and not results["r2"]["passed"]
    assert "T0:backend_state=FAIL" in results["r2"]["reason"]


def test_112_recipes_must_share_one_post_and_unrelated_fields_do_not_count(mattermost):
    mattermost["posts"] = [post(id="a", message="Blueberry Smoothie Bowl"),
                           post(id="b", message="Homemade Cereal"),
                           post(id="c", message="Chocolate PB Overnight Oats", other=LINK)]
    assert grade("112")[0] == 0


def test_112_paginates_and_preserves_independent_rubrics(mattermost):
    mattermost["posts"] = [post(id=str(i), message="unrelated") for i in range(200)]
    mattermost["posts"] += [post(id="recipes", message=RECIPES), post(id="link", message=LINK)]
    assert grade("112")[0] == 1
    assert any("page=1" in url for url in mattermost["calls"])


def test_112_deleted_channel_is_a_definitive_failure(mattermost):
    assert grade("112")[0] == 1
    mattermost["channel_deleted_at"] = START + 100
    score, nodes = grade("112")
    assert score == 0
    assert all("T0:backend_state=FAIL" in node["reason"] for node in nodes.values())


def test_112_normalizes_recipe_case_and_punctuation(mattermost):
    mattermost["posts"][0]["message"] = "BLUEBERRY smoothie-bowl; Homemade Cereal; Chocolate PB overnight oats. " + LINK
    assert grade("112")[0] == 1


def test_112_missing_execution_start_is_inconclusive(mattermost):
    score, nodes = grade("112", EvalContext(task_config=TASKS["112"]))
    assert score == 0
    assert all("INCONCLUSIVE" in node["reason"] for node in nodes.values())


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_112_probe_errors_do_not_pass_or_reuse_previous_success(mattermost, status):
    assert grade("112")[0] == 1
    mattermost["status"] = status
    score, nodes = grade("112")
    assert score == 0
    assert all("INCONCLUSIVE" in node["reason"] for node in nodes.values())


def flight(origin="YUL", destination="ATL", **changes):
    return {"id": "flight", "origin": origin, "destination": destination, "departure": "2026-06-15T10:00:00",
            "stops": 0, "total_duration_minutes": 182, **changes}


def search(event_id, origin, destination, offers):
    return {"id": event_id, "kind": "search", "started_at_ms": START + 10,
            "trip_type": "one_way", "legs": [{"origin": origin, "destination": destination}], "offers": offers}


def complete_flight_state():
    return {"schema_version": 1, "generation": "execution-one", "discarded_through_ms": None,
            "events": [search("research", "YUL", "ATL", [flight()]),
                       search("selected", "ATL", "BOS", [flight("ATL", "BOS")]),
                       {"id": "book", "kind": "booking", "started_at_ms": START + 20, "booking_id": "booking"}],
            "bookings": [{"booking_id": "booking", "status": "confirmed", "outbound_flight": flight("ATL", "BOS"),
                          "return_flight": None, "multi_city_flights": []}]}


@pytest.fixture
def flights(monkeypatch):
    current = {"state": complete_flight_state(), "status": 200}
    def send(_self, spec, context):
        assert spec["url"] == "__FLIGHT-SEARCH__/api/eval/state"
        assert spec["auth_mode"] == "eval_token"
        result = response(current["state"], current["status"])
        if current.get("malformed_json"):
            result._content = b"{"
        return result
    monkeypatch.setattr(BackendStateEvaluator, "_send", send)
    return current


def test_344_stability_partial_credit_reversal_and_reset(flights):
    ctx = EvalContext(task_config=TASKS["344"], task_start_time_ms=START)
    for step in range(4):
        ctx.trajectory.append({"action": "noop()", "obs": {"axtree_txt": str(step)}})
        assert grade("344", ctx)[0] == 1
    flights["state"]["bookings"][0]["status"] = "cancelled"
    assert grade("344")[0] == pytest.approx(2 / 3)
    flights["state"]["bookings"] = []
    assert grade("344")[0] == pytest.approx(2 / 3)
    flights["state"]["events"].append(search("changed-choice", "LAX", "BOS", []))
    score, nodes = grade("344")
    assert score == pytest.approx(1 / 3)
    assert nodes["r3"]["reason"] == "dependency failed: r2"
    flights["state"] = {**complete_flight_state(), "generation": "new-reset", "events": [], "bookings": []}
    score, nodes = grade("344", ctx)
    assert score == 0 and nodes["r2"]["reason"] == "dependency failed: r1"
    flights["state"] = complete_flight_state()
    assert grade("344")[0] == 1


@pytest.mark.parametrize("changes,expected", [
    ({"total_duration_minutes": 179}, 0), ({"total_duration_minutes": 180}, 1),
    ({"total_duration_minutes": 240}, 1), ({"total_duration_minutes": 241}, 0),
    ({"total_duration_minutes": "182"}, 0), ({"stops": 1}, 0),
    ({"origin": "ATL", "destination": "YUL"}, 0),
])
def test_344_research_requires_actual_outbound_nonstop_results(flights, changes, expected):
    flights["state"]["events"][0]["offers"][0].update(changes)
    assert grade("344")[0] == expected


def test_344_catalogue_or_claim_without_search_does_not_count(flights):
    flights["state"]["events"][0]["offers"] = []
    assert grade("344")[0] == 0


@pytest.mark.parametrize("change", ["wrong_origin", "wrong_destination", "return", "multi_city", "unrecorded", "pending"])
def test_344_booking_requires_same_city_direction_confirmation_and_one_way(flights, change):
    booking = flights["state"]["bookings"][0]
    if change == "wrong_origin":
        booking["outbound_flight"]["origin"] = "MIA"  # Eligible but not researched.
    elif change == "wrong_destination":
        booking["outbound_flight"]["destination"] = "YUL"
    elif change == "return":
        booking["return_flight"] = flight("BOS", "ATL")
    elif change == "multi_city":
        booking["multi_city_flights"] = [flight("ATL", "BOS")]
    elif change == "unrecorded":
        booking["booking_id"] = "earlier-execution"
    else:
        booking["status"] = "pending"
    assert grade("344")[0] == pytest.approx(2 / 3)


def test_344_booking_has_no_duration_or_nonstop_constraint(flights):
    flights["state"]["bookings"][0]["outbound_flight"].update(total_duration_minutes=400, stops=1)
    assert grade("344")[0] == 1


def test_344_live_booking_survives_unrelated_searches(flights):
    flights["state"]["events"].append(search("browse", "LAX", "BOS", []))
    assert grade("344")[0] == 1


def test_344_latest_route_cannot_borrow_an_eligible_origin_from_another_leg(flights):
    flights["state"]["bookings"] = []
    later = search("different-choice", "LAX", "BOS", [])
    later["legs"].append({"origin": "ATL", "destination": "LAX"})
    flights["state"]["events"].append(later)
    assert grade("344")[0] == pytest.approx(1 / 3)


def test_344_old_booking_event_cannot_borrow_another_current_creation(flights):
    flights["state"]["events"][-1]["started_at_ms"] = START - 1
    flights["state"]["events"].append({
        "kind": "booking", "id": "other-creation", "booking_id": "different-booking", "started_at_ms": START + 100,
    })
    assert grade("344")[0] == pytest.approx(2 / 3)


def test_344_older_truncation_and_unrelated_new_search_preserve_current_completion(flights):
    flights["state"]["discarded_through_ms"] = START - 1
    flights["state"]["bookings"] = []
    flights["state"]["events"].append(search("unrelated", "LAX", "JFK", []))
    assert grade("344")[0] == pytest.approx(2 / 3)


def test_344_route_selection_keeps_case_insensitive_airport_codes(flights):
    flights["state"]["bookings"] = []
    flights["state"]["events"][1]["legs"] = [{"origin": "atl", "destination": "bos"}]
    assert grade("344")[0] == pytest.approx(2 / 3)


def test_344_earlier_execution_cannot_pass(flights):
    for event in flights["state"]["events"]:
        event["started_at_ms"] = START - 1
    assert grade("344")[0] == 0


def test_344_shared_backend_uses_current_worker_url_and_token(monkeypatch):
    state = complete_flight_state()
    calls = []
    monkeypatch.setenv("WP_EVAL_TOKEN", "flight-test-token")
    monkeypatch.setenv("WP_FLIGHT_SEARCH_URL", "http://flight-w1.localhost:8080")

    def request(self, method, url, auth, headers, body):
        assert method == "GET" and auth is None and body is None
        assert headers["X-Eval-Token"] == "flight-test-token"
        calls.append(url)
        return response(state)

    monkeypatch.setattr(BackendStateEvaluator, "_make_request", request)
    score, nodes = grade("344")
    assert score == 1
    assert calls == ["http://flight-w1.localhost:8080/api/eval/state"] * 3
    assert all("decided_by=T0:backend_state" in node["reason"] for node in nodes.values())
    assert all("evidence_sha256=" in node["reason"] for node in nodes.values())
    calls.clear()
    monkeypatch.setenv("WP_FLIGHT_SEARCH_URL", "https://flight-w2.localhost")
    state["bookings"][0]["status"] = "cancelled"
    assert grade("344")[0] == pytest.approx(2 / 3)
    assert calls == ["https://flight-w2.localhost/api/eval/state"] * 3


@pytest.mark.parametrize("bad", ["missing_endpoint", "auth", "server", "schema", "truncated", "malformed", "non_json", "missing_start"])
@pytest.mark.parametrize("verdict", ["pass", "fail"])
def test_344_inconclusive_evidence_uses_fallback_and_records_reason(flights, monkeypatch, bad, verdict):
    assert grade("344")[0] == 1
    ctx = EvalContext(task_config=TASKS["344"], task_start_time_ms=START)
    if bad in {"missing_endpoint", "auth", "server"}:
        flights["status"] = {"missing_endpoint": 404, "auth": 403, "server": 500}[bad]
    elif bad == "schema":
        flights["state"]["schema_version"] = 0
    elif bad == "truncated":
        flights["state"]["discarded_through_ms"] = START
    elif bad == "malformed":
        flights["state"]["events"][0]["started_at_ms"] = "invalid"
    elif bad == "non_json":
        flights["malformed_json"] = True
    else:
        ctx.task_start_time_ms = None
    called = []

    def judge(rubric, context, model):
        called.append(context.judge_node_id)
        assert "INCONCLUSIVE" in context.judge_strategy_trace[0]
        return verdict, "scripted fallback verdict"

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    score, nodes = grade("344", ctx)
    assert score == (1 if verdict == "pass" else 0)
    assert called == (["r1", "r2", "r3"] if verdict == "pass" else ["r1"])
    for node_id in called:
        assert "decided_by=T2:llm_judge [escalated]" in nodes[node_id]["reason"]
        assert "T0:backend_state=INCONCLUSIVE" in nodes[node_id]["reason"]
    if verdict == "fail":
        assert nodes["r2"]["reason"] == "dependency failed: r1"


@pytest.mark.parametrize("target", ["r1", "r2", "r3"])
@pytest.mark.parametrize("verdict", ["pass", "fail"])
def test_344_only_the_inconclusive_node_reaches_tier_two(flights, monkeypatch, target, verdict):
    send = BackendStateEvaluator._send
    def targeted_error(self, spec, context):
        return response({}, 503) if context.judge_node_id == target else send(self, spec, context)
    monkeypatch.setattr(BackendStateEvaluator, "_send", targeted_error)
    called = []
    def judge(rubric, context, model):
        called.append(context.judge_node_id)
        return verdict, "scripted fallback verdict"
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    score, nodes = grade("344")
    assert called == [target]
    expected = 1 if verdict == "pass" else {"r1": 0, "r2": 1 / 3, "r3": 2 / 3}[target]
    assert score == pytest.approx(expected)
    assert "T2:llm_judge" in nodes[target]["reason"]


def test_344_recovered_backend_failure_overrides_previous_fallback_success(flights, monkeypatch):
    called = []
    def judge(rubric, context, model):
        called.append(context.judge_node_id)
        return "pass", "scripted fallback success"
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    ctx = EvalContext(task_config=TASKS["344"], task_start_time_ms=START)
    flights["status"] = 503
    assert grade("344", ctx)[0] == 1
    assert called == ["r1", "r2", "r3"]
    called.clear()
    flights["status"] = 200
    flights["state"]["bookings"][0]["status"] = "cancelled"
    score, nodes = grade("344", ctx)
    assert score == pytest.approx(2 / 3)
    assert "T0:backend_state=FAIL" in nodes["r3"]["reason"]
    assert called == []


@pytest.mark.parametrize("task_id", ["112", "344"])
def test_dag_dependencies_intent_and_equal_scoring_are_preserved(task_id):
    old = next(task for task in json.loads((Path(__file__).parent / "fixtures/issue83_legacy_tasks.json").read_text())
               if task["task_id"] == task_id)
    task = TASKS[task_id]
    assert task["intent"] == old["intent"]
    assert task["sites"] == old["sites"]
    for current, previous in zip(task["eval"]["nodes"], old["eval"]["nodes"], strict=True):
        assert {key: current[key] for key in ("id", "depends_on")} == {
            key: previous[key] for key in ("id", "depends_on")}
        assert "weight" not in current
        strategies = current["eval_config"]["strategies"]
        assert strategies[0]["trust"] == "both"
        assert strategies[0]["type"] == "backend_state"
        if task_id == "344":
            assert len(strategies) == 2
            assert strategies[1] == previous["eval_config"]["strategies"][-1]
            assert all(check["type"] == "json_predicate" for check in strategies[0]["config"]["checks"])
        else:
            assert len(strategies) == 1
