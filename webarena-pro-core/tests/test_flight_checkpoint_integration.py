"""Current task 344 DAG against real Flight Search handlers and route data.

Run with the website's requirements installed; no containers or model calls.
"""
import importlib
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from test_deterministic_checkpoints import TASKS, response
from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
from webarena_pro_core.eval import llm_judge


def test_complete_research_choose_book_repeat_and_undo(monkeypatch):
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", lambda *_: pytest.fail("Definitive state must not reach Tier 2"))
    website = Path(__file__).resolve().parents[2] / "websites/flight-search"
    monkeypatch.syspath_prepend(str(website))
    main = importlib.import_module("backend.main")
    benchmark = importlib.import_module("backend.benchmark")
    store = importlib.import_module("backend.booking_store")
    evidence = importlib.import_module("backend.eval_state")
    monkeypatch.setenv("WP_EVAL_TOKEN", "integration-token")
    monkeypatch.setattr(benchmark, "BENCHMARK_MODE", True)
    store.reset_bookings()
    ctx = EvalContext(task_config=TASKS["344"], task_start_time_ms=evidence.now_ms())
    dag = DAGEvaluator(parse_eval_dag(TASKS["344"]["eval"]))
    with TestClient(main.app) as client:
        assert client.post("/api/auth/verify", json={"passkey": "flyingagents"}).status_code == 200

        def send(_self, spec, _context):
            assert spec["url"] == "__FLIGHT-SEARCH__/api/eval/state"
            result = client.get("/api/eval/state", headers={"X-Eval-Token": "integration-token"})
            return response(result.json(), result.status_code)
        monkeypatch.setattr(BackendStateEvaluator, "_send", send)

        def grade():
            score, nodes = dag.evaluate(ctx)
            assert ctx.judge_audits == []
            return score

        def search(origin, destination):
            result = client.post("/api/search", json={
                "trip_type": "one_way", "legs": [{"origin": origin, "destination": destination, "date": "2026-06-15"}],
                "filters": {"max_stops": 0},
            })
            assert result.status_code == 200
            return result.json()["outbound_flights"]

        assert grade() == 0
        assert search("YUL", "ATL")
        assert grade() == pytest.approx(1 / 3)
        flights = search("ATL", "BOS")
        assert grade() == pytest.approx(2 / 3)
        result = client.post("/api/booking", json={
            "passenger": {"first_name": "Jane", "last_name": "Smith", "email": "jane@example.test", "phone": "123"},
            "payment": {"cardholder_name": "Jane Smith", "card_number": "4111111111111111", "expiry_date": "12/27", "cvv": "123"},
            "outbound_flight": flights[0],
        })
        assert result.status_code == 200
        assert [grade() for _ in range(3)] == [1, 1, 1]
        store._bookings[0]["status"] = "cancelled"
        assert grade() == pytest.approx(2 / 3)
        store._bookings.clear()
        assert grade() == pytest.approx(2 / 3)
        assert search("LAX", "BOS")
        assert grade() == pytest.approx(1 / 3)
        client.post("/api/reset")
        assert grade() == 0
    store.reset_bookings()
