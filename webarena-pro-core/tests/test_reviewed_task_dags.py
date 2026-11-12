"""Coverage and adversarial fixtures for the reviewed October additions."""
import copy
import json
from pathlib import Path

import pytest
import requests

from webarena_pro_core.eval.answer_match import AnswerMatchEvaluator
from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
from webarena_pro_core.eval import llm_judge


CONFIG = Path(__file__).parents[1] / "src/webarena_pro_core/config"
TASKS = {task["task_id"]: task for path in CONFIG.glob("*.raw.json")
         for task in json.loads(path.read_text())}
TASKS.update({task["task_id"]: task
              for task in json.loads((CONFIG / "splits/dev.json").read_text())["tasks"]})
DAGS = {tid: task["eval"] for tid, task in TASKS.items()}


def strategy(task_id, node=0):
    return DAGS[task_id]["nodes"][node]["eval_config"]["strategies"][0]


def backend_matches(task_id, payload, node=0, *, sorted_keys=False):
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(payload, sort_keys=sorted_keys, separators=(",", ":")).encode()
    evaluator = BackendStateEvaluator()
    config = strategy(task_id, node)["config"]
    return all(evaluator._run_check(check, response)[0] for check in config["checks"])


def test_packaged_additions_have_matching_raw_tasks_and_dags():
    raw = [task for path in CONFIG.glob("*.raw.json") for task in json.loads(path.read_text())]
    raw += json.loads((CONFIG / "splits/dev.json").read_text())["tasks"]
    by_task_id = {task["task_id"]: task for task in raw}
    assert len(raw) == len(by_task_id) == len(DAGS) == 400
    assert set(by_task_id) == set(DAGS)
    added_ids = {f"{task_id:03d}" for task_id in [*range(300, 346), *range(403, 421)]}
    revised_ids = {"028", "256"}
    selected = [task for task in raw if task["task_id"] in added_ids | revised_ids]
    assert {task["task_id"] for task in selected} == added_ids | revised_ids
    for source in selected:
        task_id = source["task_id"]
        dag = DAGS[task_id]
        assert "intent" not in dag
        assert source["eval"] == dag
        assert all(node["eval_config"]["rubric"].strip() for node in dag["nodes"])
        assert len(DAGEvaluator(parse_eval_dag(dag))._topological_sort()) == len(dag["nodes"])
        assert dag["operator"] == "AND" and dag["scoring"] == "partial"
        for node in dag["nodes"]:
            strategies = node["eval_config"]["strategies"]
            assert node["type"] == "tiered"
            if task_id == "344":
                assert len(strategies) == 2
                assert strategies[0]["type"] == "backend_state"
                assert strategies[0]["config"]["api"] == "eval_state"
                assert strategies[0]["config"]["site"] == "flight-search"
                assert strategies[0]["trust"] == "both"
                assert strategies[1]["type"] == "llm_judge"
                assert strategies[1]["tier"] == 2
                continue
            assert strategies[-1]["type"] == "llm_judge"
            for strategy in strategies[:-1]:
                if task_id == "303":
                    # Exact saved CardDAV identities/details are authoritative;
                    # unlike the older broad presence heuristics, failure stands.
                    assert strategy["type"] == "backend_state"
                    assert strategy["config"]["api"] == "contacts_report"
                    assert strategy["trust"] == "both"
                elif task_id == "310":
                    # Stable file IDs establish creation independently of names.
                    assert strategy["type"] == "backend_state"
                    assert strategy["config"]["baseline_ref"] == "mydrive_files"
                    assert strategy["trust"] == "both"
                else:
                    assert strategy["trust"] == "pass_only"


def test_watch_later_requires_all_videos_and_does_not_match_history():
    task_id = "313"
    rows = [{"username": "seed_user", "video_id": video} for video in ["fv785", "fv1071", "fv1290"]]
    assert backend_matches(task_id, {"watch_later": rows}, sorted_keys=True)
    assert not backend_matches(task_id, {"watch_later": rows[:2]}, sorted_keys=True)
    assert not backend_matches(task_id, {"watch_later": [], "history": rows}, sorted_keys=True)
    assert not backend_matches(task_id, {"watch_later": [{**r, "username": "someone_else"} for r in rows]}, sorted_keys=True)


@pytest.mark.parametrize("video_id", ["fv258", "fv357"])
def test_watch_later_accepts_duplicate_catalogue_titles(video_id):
    assert backend_matches("318", {"watch_later": [{"username": "seed_user", "video_id": video_id}]}, 4, sorted_keys=True)


def test_face_video_exclusion_gate_cannot_credit_empty_or_extra_watch_later_lists():
    task_id = "321"
    selected = {"username": "seed_user", "video_id": "fv678"}
    assert backend_matches(task_id, {"watch_later": [selected]}, 2, sorted_keys=True)
    assert not backend_matches(task_id, {"watch_later": []}, 2, sorted_keys=True)
    assert not backend_matches(task_id, {"watch_later": [selected, {**selected, "video_id": "fv275"}]}, 2, sorted_keys=True)
    assert DAGS[task_id]["nodes"][2]["depends_on"] == ["r2"]


def test_comments_require_both_videos_and_the_current_author():
    task_id = "316"
    rows = [{"id": i, "video_id": vid, "username": "seed_user",
             "text": "Check out my channel: @baseballRUS", "created_at": "2026-10-04"}
            for i, vid in enumerate(["fv1353", "fv1160"])]
    assert backend_matches(task_id, {"comments": rows}, sorted_keys=True)
    assert not backend_matches(task_id, {"comments": rows[:1]}, sorted_keys=True)
    assert not backend_matches(task_id, {"comments": [{**r, "username": "someone_else"} for r in rows]}, sorted_keys=True)
    assert not backend_matches(task_id, {"comments": [{**r, "text": "Unrelated comment"} for r in rows]}, sorted_keys=True)
    assert not backend_matches(task_id, {"comments": [{**r, "text": "Do not follow @baseballRUS"} for r in rows]}, sorted_keys=True)


def test_folk_playlist_requires_exactly_four_correct_songs_in_that_playlist():
    task_id = "308"
    payload = {"playlists": [{"name": "folk songs", "user_id": "aciduser", "total_duration": 2000, "song_count": 4}],
               "playlist_songs": [{"playlist": "folk songs", "song": song, "duration": 1, "position": i}
                                  for i, song in enumerate(["Underpass", "Driftwood", "Daily Signal 0912", "Brass Step"])]}
    assert backend_matches(task_id, payload, 1)
    payload["playlists"][0]["song_count"] = 5
    assert not backend_matches(task_id, payload, 1)
    payload["playlists"][0]["song_count"] = 4
    payload["playlist_songs"][-1]["playlist"] = "unrelated"
    assert not backend_matches(task_id, payload, 1)


def test_cassette_playlist_requires_both_songs_not_catalogue_presence():
    rows = [{"playlist": "CASSETTE_SET", "song": title} for title in ["Faultline Shift", "Velvet Circuit"]]
    assert backend_matches("300", {"playlist_songs": rows})
    assert not backend_matches("300", {"playlist_songs": rows[:1]})
    assert not backend_matches("300", {"songs": [{"title": "Faultline Shift"}, {"title": "Velvet Circuit"}]})


def test_booking_joins_origin_destination_and_date_on_the_same_flight():
    task_id = "301"
    flight = {"origin": "YUL", "destination": "JFK", "departure": "2026-08-16T09:00:00"}
    assert backend_matches(task_id, [{"status": "confirmed", "outbound_flight": flight}], 1)
    assert not backend_matches(task_id, [{"outbound_flight": {**flight, "departure": "2026-08-17T09:00:00"}}], 1)
    assert not backend_matches(task_id, [{"outbound_flight": {**flight, "destination": "LAX"}},
                                       {"outbound_flight": {**flight, "origin": "BOS"}}], 1)
    assert not backend_matches(task_id, [{"outbound_flight": {"segments": [flight], "origin": "YUL", "destination": "LAX"}}], 1)


def test_answer_gates_reject_substrings_and_wrong_order():
    evaluator = AnswerMatchEvaluator()
    def matches(task_id, text):
        context = EvalContext(last_action=f"send_msg_to_user({text!r})")
        return bool(evaluator.evaluate(strategy(task_id)["config"], context))
    assert matches("317", "9")
    assert not matches("317", "19")
    assert not matches("315", "The bird is not Vinnie")
    correct = strategy("312")["config"]["exact_match"]
    assert matches("312", correct)
    assert not matches("312", ", ".join(reversed(correct.split(", "))))


def test_cross_site_content_has_dependencies_and_does_not_use_weak_presence_gates():
    for task_id in ["311", "310", "307", "304", "324"]:
        content = DAGS[task_id]["nodes"][1]
        assert content["depends_on"] == ["r1"]
        assert [s["type"] for s in content["eval_config"]["strategies"]] == ["llm_judge"]
    # The ambiguous source wording must not reward creating the wrong artifact.
    contact_judge = strategy("303")["config"]["rubric"]
    assert "Nextcloud Contacts" in contact_judge
    assert "Creating a document alone does not satisfy" in contact_judge


@pytest.fixture
def workstation_invoice():
    return {"data": {
        "customer_name": "Maple Lantern Architecture Inc.",
        "remarks": "Ottawa studio workstation setup",
        "currency": "EUR", "net_total": 7900,
        "posting_date": "2026-08-07", "due_date": "2026-08-21",
        "selling_price_list": "Standard Selling", "docstatus": 1,
        "items": [
            {"item_code": code, "qty": qty, "rate": rate}
            for code, qty, rate in [
                ("DESK-001", 4, 430), ("MONITOR-001", 8, 590),
                ("OFFICE-CHAIR-001", 4, 150), ("DOCKING-STATION-001", 4, 181),
                ("CABLE-MGMT-001", 4, 34),
            ]
        ],
    }}


def test_invoice_items_bind_each_quantity_and_price_and_reject_extra_lines(workstation_invoice):
    task_id = "322"
    assert backend_matches(task_id, workstation_invoice)
    for field, value in [("item_code", "UNRELATED-001"), ("qty", 5), ("rate", 431)]:
        wrong = copy.deepcopy(workstation_invoice)
        wrong["data"]["items"][0][field] = value
        assert not backend_matches(task_id, wrong)
    extra = copy.deepcopy(workstation_invoice)
    extra["data"]["items"].append({"item_code": "EXTRA", "qty": 1, "rate": 0})
    assert not backend_matches(task_id, extra)
    missing = copy.deepcopy(workstation_invoice)
    missing["data"]["items"].pop()
    assert not backend_matches(task_id, missing)


@pytest.mark.parametrize("node,field,value", [
    (0, "customer_name", "Unrelated customer"), (0, "currency", "CAD"),
    (1, "net_total", 79000), (1, "currency", "CAD"),
    (2, "posting_date", "2026-08-08"), (2, "due_date", "2026-08-22"),
    (2, "selling_price_list", "Standard Buying"), (2, "docstatus", 0),
    (4, "docstatus", 0), (4, "docstatus", 2),
    (4, "remarks", "Unrelated invoice"),
])
def test_invoice_checks_reject_wrong_values(workstation_invoice, node, field, value):
    task_id = "322"
    assert backend_matches(task_id, workstation_invoice, node)
    workstation_invoice["data"][field] = value
    assert not backend_matches(task_id, workstation_invoice, node)


def test_invoice_customer_must_be_the_named_company():
    task_id = "322"
    customer = {"customer_name": "Maple Lantern Architecture Inc.", "customer_type": "Company"}
    assert backend_matches(task_id, {"data": [customer]}, 3)
    assert not backend_matches(task_id, {"data": [{**customer, "customer_type": "Individual"}]}, 3)
    assert not backend_matches(task_id, {"data": [{**customer, "customer_name": "Unrelated Company"}]}, 3)


@pytest.mark.parametrize("answer,expected", [
    ("$0.75; YES", True), ("$10.75; YES", False),
    ("-$0.75; NO", False), ("Not $0.75; YES", False),
])
def test_budget_answer_gate_rejects_wrong_amounts_and_negation(answer, expected):
    result = AnswerMatchEvaluator().evaluate(
        strategy("323")["config"],
        EvalContext(last_action=f"send_msg_to_user({answer!r})"),
    )
    assert bool(result) is expected


@pytest.mark.parametrize("task_id,count", [
    ("325", 6), ("326", 5),
])
def test_new_chart_and_currency_criteria_cannot_bypass_the_judge(monkeypatch, task_id, count):
    dag = DAGS[task_id]
    criteria = [node["eval_config"]["strategies"][-1]["config"]["rubric"] for node in dag["nodes"]]
    assert len(criteria) == len(set(criteria)) == count
    # No backend dump or final-answer match can establish these outcomes.
    def unexpected_request(*args, **kwargs):
        pytest.fail("These criteria must be judged from the full task evidence")
    monkeypatch.setattr(requests, "request", unexpected_request)
    context = EvalContext(task_config=TASKS[task_id])
    for accepted in [set(), {criteria[0]}, set(criteria)]:
        seen = []
        def judge(rubric, judge_context, model):
            assert judge_context is context
            seen.append(rubric)
            return ("pass" if rubric in accepted else "fail", "scripted routing test")
        monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
        score, results = DAGEvaluator(parse_eval_dag(dag)).evaluate(context)
        assert set(seen) == set(criteria) and len(seen) == count
        assert score == pytest.approx(len(accepted) / count)
        assert sum(result["passed"] for result in results.values()) == len(accepted)


OCTOBER_12_IDS = [
    "327", "328", "329",
    "330", "331", "332",
    "333", "334", "335",
    "336", "337",
]


@pytest.fixture
def clean_favorites():
    titles = [
        "I Am The Eagle", "Flying Away (Vocals)", "It's Your Choice (Lyrics by Kristina Rice)",
        "Astronaut Vocals", "Secret Agent 89 - Vocals", "Time Bomb - Vocals", "Into the Night",
        "Stayin' at Home - Vocals", "Life Is But a Dream", "More Than Numbers - Desert Ghost EP Remix",
        "Static Bloom", "Outerline", "Glass Capital", "Heat Map", "Lighthouse", "Tide Letters",
        "Underpass", "Driftwood", "Cardinal Way", "Broken Compass", "Black Coffee", "Snowfall",
        "Westbound", "Coastal Fog", "Riptide Lullaby", "Longform Signal", "Open Ledger Talk",
        "Daily Signal 0912", "Greyline", "Return Current", "Sandlight", "Velvet Circuit",
        "Brass Step", "Low Frame", "Ember Loop", "Evening Harbor", "Return Postcard",
        "Basement Years", "Dawn Signal", "Neon Want", "Interior Weather", "Low Lantern", "Weather Heart",
    ]
    assert len(set(titles)) == 43
    return [{"user_id": "aciduser", "song": title} for title in sorted(titles)]


def test_clean_song_favorites_gate_requires_the_complete_saved_user_list(clean_favorites):
    task_id = "331"
    assert backend_matches(task_id, {"favorites": clean_favorites}, sorted_keys=True)
    assert not backend_matches(task_id, {"favorites": clean_favorites[:-1]})
    assert not backend_matches(task_id, {"favorites": clean_favorites + [{"user_id": "aciduser", "song": "Halflight"}]})
    assert not backend_matches(task_id, {"favorites": clean_favorites[:-1] + [clean_favorites[0]]})
    assert not backend_matches(task_id, {"favorites": [{**row, "user_id": "someone_else"} for row in clean_favorites]})
    assert not backend_matches(task_id, {"favorites": [], "songs": clean_favorites})
    assert not backend_matches(task_id, {"favorites": [], "playlist_songs": clean_favorites})


def test_favorites_with_different_order_escalate_to_judge(monkeypatch, clean_favorites):
    task_id = "331"
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps({"favorites": list(reversed(clean_favorites))}).encode()
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: response)
    calls = []
    def judge(rubric, context, model):
        calls.append(rubric)
        return "pass", "same complete favorites in a different order"
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    score, _ = DAGEvaluator(parse_eval_dag(DAGS[task_id])).evaluate(EvalContext())
    assert score == 1.0 and len(calls) == 1


@pytest.mark.parametrize("task_id,answer,expected", [
    ("333", "63", True),
    ("333", "163", False),
    ("333", "Not 63", False),
    ("333", "63 or 64", False),
    ("332", "Glass Capital, Heat Map, Black Coffee", True),
    ("332", "Glass Capital, Heat Map", False),
    ("332", "Not Glass Capital, Heat Map, Black Coffee", False),
    ("332", "Glass Capital, Heat Map, Black Coffee, Halflight", False),
])
def test_october_12_answer_gates_reject_partial_negated_or_extra_answers(task_id, answer, expected):
    result = AnswerMatchEvaluator().evaluate(
        strategy(task_id)["config"], EvalContext(last_action=f"send_msg_to_user({answer!r})"),
    )
    assert bool(result) is expected


@pytest.mark.parametrize("task_id", OCTOBER_12_IDS)
def test_october_12_dags_route_all_rubrics_when_backend_is_unavailable(monkeypatch, task_id):
    response = requests.Response()
    response.status_code = 403
    response._content = b'{"error":"forbidden"}'
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: response)
    dag = DAGS[task_id]
    criteria = [node["eval_config"]["strategies"][-1]["config"]["rubric"] for node in dag["nodes"]]
    calls = []
    def judge(rubric, context, model):
        calls.append(rubric)
        return "pass", "scripted complete outcome"
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    score, _ = DAGEvaluator(parse_eval_dag(dag)).evaluate(EvalContext())
    assert score == 1.0
    assert len(calls) == len(criteria) and set(calls) == set(criteria)


@pytest.mark.parametrize("task_id,rejected,called,score", [
    ("327", "r1", {"r1"}, 0.0),
    ("327", "r2", {"r1", "r2"}, 1 / 3),
    ("329", "r1", {"r1"}, 0.0),
    ("330", "r2", {"r2", "r3"}, 1 / 3),
    ("334", "r2", {"r2"}, 0.0),
    ("335", "r1", {"r1"}, 0.0),
    ("336", "r1", {"r1"}, 0.0),
])
def test_october_12_missing_prerequisites_block_dependent_outcomes(monkeypatch, task_id, rejected, called, score):
    response = requests.Response()
    response.status_code = 403
    response._content = b'{"error":"forbidden"}'
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: response)
    dag = DAGS[task_id]
    ids = {node["eval_config"]["strategies"][-1]["config"]["rubric"]: node["id"] for node in dag["nodes"]}
    seen = set()
    def judge(rubric, context, model):
        node_id = ids[rubric]
        seen.add(node_id)
        return ("fail" if node_id == rejected else "pass"), "scripted missing prerequisite"
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    actual_score, _ = DAGEvaluator(parse_eval_dag(dag)).evaluate(EvalContext())
    assert actual_score == pytest.approx(score)
    assert seen == called


@pytest.mark.parametrize("task_id,node,answer,expected", [
    ("340", 2, "(Lisbon, 2), (Berlin, 3), US$1,946.00", True),
    ("340", 2, "(Berlin, 3), (Lisbon, 2), US$1,946.00", False),
    ("340", 2, "(Lisbon, 3), (Berlin, 2), US$1,946.00", False),
    ("340", 2, "(Lisbon, 2), (Berlin, 3), US$11,946.00", False),
    ("340", 2, "(Lisbon, 2), (Berlin, 3), C$1,946.00", False),
    ("340", 2, "Not (Lisbon, 2), (Berlin, 3), US$1,946.00", False),
    ("341", 0, "Toronto; $206.54", True),
    ("341", 0, "Toronto; $1206.54", False),
    ("341", 0, "Montreal; $206.54", False),
    ("341", 0, "Not Toronto; $206.54", False),
    ("341", 0, "Toronto; $206.54 or Chicago; $200", False),
])
def test_date_validated_answer_gates_reject_wrong_routes_prices_and_negation(task_id, node, answer, expected):
    result = AnswerMatchEvaluator().evaluate(
        strategy(task_id, node)["config"], EvalContext(last_action=f"send_msg_to_user({answer!r})"),
    )
    assert bool(result) is expected


@pytest.mark.parametrize("task_id,answer,rejected,called,score", [
    ("338", "BFD: 548", {"r1", "r2"}, {"r1", "r2"}, 0),
    ("338", "BFD: 548", {"r1"}, {"r1", "r2"}, 1 / 2),
    ("339", "C$608; AC8436, AC4776; UA168, UA9009", {"r1", "r2", "r3"}, {"r1", "r2", "r3"}, 0),
    ("339", "Created a piggy bank for C$608", {"r2"}, {"r1", "r2", "r3"}, 1 / 2),
    ("339", "Created a piggy bank for C$608", {"r4"}, {"r1", "r2", "r3", "r4"}, 3 / 4),
    ("339", "Created a piggy bank for C$608", set(), {"r1", "r2", "r3", "r4"}, 1),
    ("340", "(Lisbon, 2), (Berlin, 3), US$1,946.00", {"r1"}, {"r1", "r2"}, 1 / 3),
    ("340", "(Lisbon, 2), (Berlin, 3), US$1,946.00", {"r2"}, {"r1", "r2"}, 1 / 3),
    ("340", "(Lisbon, 2), (Berlin, 3), US$1,946.00", set(), {"r1", "r2"}, 1),
    ("341", "Toronto; $206.54", set(), set(), 1),
    ("341", "Toronto is cheapest, with a total of $206.54.", set(), {"r1"}, 1),
    ("341", "Toronto; $1206.54", {"r1"}, {"r1"}, 0),
])
def test_date_validated_dags_require_research_and_creation_evidence(monkeypatch, task_id, answer, rejected, called, score):
    dag = DAGS[task_id]
    ids = {node["eval_config"]["strategies"][-1]["config"]["rubric"]: node["id"] for node in dag["nodes"]}
    context = EvalContext(last_action=f"send_msg_to_user({answer!r})", task_config=TASKS[task_id])
    seen = set()

    def judge(rubric, judge_context, model):
        assert judge_context is context
        node_id = ids[rubric]
        seen.add(node_id)
        return ("fail" if node_id in rejected else "pass"), "scripted trajectory evidence"

    def unexpected_request(*args, **kwargs):
        pytest.fail("An amount-only backend check cannot establish research or creation evidence")

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    monkeypatch.setattr(requests, "request", unexpected_request)
    actual_score, _ = DAGEvaluator(parse_eval_dag(dag)).evaluate(context)
    assert actual_score == pytest.approx(score)
    assert seen == called


@pytest.mark.parametrize("task_id,rejected,called,score", [
    ("342", set(), {"r1", "r2", "r3", "r4"}, 1),
    ("342", {"r1"}, {"r1"}, 0),
    ("342", {"r2"}, {"r1", "r2"}, 1 / 4),
    ("342", {"r3"}, {"r1", "r2", "r3", "r4"}, 3 / 4),
    ("342", {"r4"}, {"r1", "r2", "r3", "r4"}, 3 / 4),
    ("343", set(), {"r1", "r2", "r3", "r4", "r5", "r6", "r7"}, 1),
])
def test_reapproved_dags_require_context_and_block_missing_prerequisites(monkeypatch, task_id, rejected, called, score):
    # Task 344 now exercises real state and all dependency gates in
    # test_deterministic_checkpoints.py and test_flight_checkpoint_integration.py.
    dag = DAGS[task_id]
    ids = {node["eval_config"]["strategies"][-1]["config"]["rubric"]: node["id"] for node in dag["nodes"]}
    # Even a final answer repeating every approved rubric must reach the judge.
    answer = "; ".join(node["eval_config"]["rubric"] for node in dag["nodes"])
    context = EvalContext(last_action=f"send_msg_to_user({answer!r})", task_config=TASKS[task_id])
    seen = set()

    def judge(rubric, judge_context, model):
        assert judge_context is context
        node_id = ids[rubric]
        seen.add(node_id)
        return ("fail" if node_id in rejected else "pass"), "scripted saved-state and trajectory evidence"

    def unexpected_request(*args, **kwargs):
        pytest.fail("An unbound backend match cannot establish the selected month, new comment, or chosen origin")

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    monkeypatch.setattr(requests, "request", unexpected_request)
    actual_score, _ = DAGEvaluator(parse_eval_dag(dag)).evaluate(context)
    assert actual_score == pytest.approx(score)
    assert seen == called


@pytest.mark.parametrize("accepted", [f"r{i}" for i in range(1, 8)])
def test_reapproved_budget_categories_receive_independent_partial_credit(monkeypatch, accepted):
    dag = DAGS["343"]
    ids = {node["eval_config"]["strategies"][-1]["config"]["rubric"]: node["id"] for node in dag["nodes"]}
    seen = []

    def judge(rubric, context, model):
        node_id = ids[rubric]
        seen.append(node_id)
        return ("pass" if node_id == accepted else "fail"), "only one category saved for the correct month"

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    score, results = DAGEvaluator(parse_eval_dag(dag)).evaluate(EvalContext())
    assert score == pytest.approx(1 / 7)
    assert len(seen) == len(set(seen)) == 7
    assert {node_id for node_id, result in results.items() if result["passed"]} == {accepted}


@pytest.mark.parametrize("message_sent", [False, True])
def test_retained_podcast_task_scores_only_the_current_dm_rubric(monkeypatch, message_sent):
    task_id = "028"
    dag = DAGS[task_id]
    # A matching title in the final answer cannot substitute for a sent DM.
    # A valid DM can receive full credit without the removed transcription step.
    context = EvalContext(last_action="send_msg_to_user('Trailer Static')")
    calls = []

    def judge(rubric, judge_context, model):
        assert judge_context is context
        calls.append(rubric)
        return ("pass" if message_sent else "fail"), "scripted verification of the actual DM"

    def unexpected_request(*args, **kwargs):
        pytest.fail("A message-title substring cannot establish the sender and requested DM outcome")

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    monkeypatch.setattr(requests, "request", unexpected_request)
    score, results = DAGEvaluator(parse_eval_dag(dag)).evaluate(context)
    assert score == float(message_sent)
    assert len(calls) == len(results) == 1
    assert results["r1"]["passed"] is message_sent


@pytest.mark.parametrize("task_id", ["345", "256"])
@pytest.mark.parametrize("rejected,called,expected", [
    (set(), {"r1", "r2"}, 1),
    ({"r1"}, {"r1"}, 0),
    ({"r2"}, {"r1", "r2"}, 0.5),
])
def test_older_rereviews_require_actual_outcomes_in_the_same_context(monkeypatch, task_id, rejected, called, expected):
    dag = DAGS[task_id]
    ids = {node["eval_config"]["strategies"][-1]["config"]["rubric"]: node["id"] for node in dag["nodes"]}
    context = EvalContext(last_action="send_msg_to_user('I saved two AI posts and sent the meeting details')")
    seen = set()

    def judge(rubric, judge_context, model):
        assert judge_context is context
        node_id = ids[rubric]
        seen.add(node_id)
        return ("fail" if node_id in rejected else "pass"), "scripted actual saved state and recipient/group evidence"

    def unexpected_request(*args, **kwargs):
        pytest.fail("Unbound message substrings or counts across unrelated groups cannot prove these outcomes")

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    monkeypatch.setattr(requests, "request", unexpected_request)
    score, results = DAGEvaluator(parse_eval_dag(dag)).evaluate(context)
    assert score == pytest.approx(expected)
    assert seen == called
    assert len(results) == 2
