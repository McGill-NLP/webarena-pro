"""Real search/booking handlers expose reset-scoped, authenticated evidence."""
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import benchmark, booking_store, eval_state, main


class EvaluationStateTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"WP_EVAL_TOKEN": "test-eval-token", "REQUIRE_PASSKEY": "true"}))
        self.enterContext(patch.object(benchmark, "BENCHMARK_MODE", True))
        self.client = self.enterContext(TestClient(main.app))
        booking_store.reset_bookings()
        self.addCleanup(booking_store.reset_bookings)
        self.headers = {"X-Eval-Token": "test-eval-token"}
        self.assertEqual(self.client.post("/api/auth/verify", json={"passkey": "flyingagents"}).status_code, 200)

    def state(self):
        result = self.client.get("/api/eval/state", headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def search(self, origin="YUL", destination="ATL", **changes):
        query = {"trip_type": "one_way", "legs": [{"origin": origin, "destination": destination, "date": "2026-06-15"}],
                 "filters": {"max_stops": 0}, **changes}
        result = self.client.post("/api/search", json=query)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def book(self, flight):
        result = self.client.post("/api/booking", json={
            "passenger": {"first_name": "Jane", "last_name": "Smith", "email": "jane@example.test", "phone": "123"},
            "payment": {"cardholder_name": "Jane Smith", "card_number": "4111111111111111", "expiry_date": "12/27", "cvv": "123"},
            "outbound_flight": flight,
        })
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_eval_token_is_required_even_with_passkey_or_disabled_gate(self):
        self.assertEqual(self.client.get("/api/eval/state").status_code, 403)
        self.assertEqual(self.client.get("/api/eval/state", headers={"X-Eval-Token": "wrong"}).status_code, 403)
        with patch.dict(os.environ, {"REQUIRE_PASSKEY": "false"}):
            self.assertEqual(self.client.get("/api/eval/state").status_code, 403)
        with patch.dict(os.environ, {"WP_EVAL_TOKEN": ""}):
            self.assertEqual(self.client.get("/api/eval/state", headers=self.headers).status_code, 503)

    def test_records_actual_filtered_results_without_personal_or_payment_data(self):
        before = eval_state.now_ms()
        result = self.search()
        event = self.state()["events"][0]
        self.assertGreaterEqual(event["started_at_ms"], before)
        self.assertEqual(event["offers"], [eval_state.flight_evidence(f) for f in result["outbound_flights"]])
        self.assertTrue(any(180 <= f["total_duration_minutes"] <= 240 for f in event["offers"]))
        booking = self.book(self.search("ATL", "BOS")["outbound_flights"][0])
        state = self.state()
        self.assertEqual(state["events"][-1]["booking_id"], booking["booking_id"])
        self.assertEqual(state["bookings"][0]["status"], "confirmed")
        self.assertNotIn("payment", str(state))
        self.assertNotIn("jane@example.test", str(state))
        self.assertEqual(self.state(), state)  # Reading evidence is side-effect free.

    def test_empty_search_does_not_invent_available_results(self):
        self.search(filters={"max_price": 1})
        self.assertEqual(self.state()["events"][0]["offers"], [])

    def test_invalid_search_and_failed_payment_do_not_create_evidence(self):
        result = self.client.post("/api/search", json={"legs": [{"origin": "XXX", "destination": "ATL", "date": "2026-06-15"}]})
        self.assertEqual(result.status_code, 404)
        self.assertEqual(self.state()["events"], [])
        self.assertEqual(self.client.post("/api/booking", json={}).status_code, 422)
        self.assertEqual(self.state()["bookings"], [])

    def test_return_and_multi_city_results_are_recorded(self):
        for trip_type in ("round_trip", "multi_city"):
            booking_store.reset_bookings()
            result = self.search(trip_type=trip_type, legs=[
                {"origin": "YUL", "destination": "ATL", "date": "2026-06-15"},
                {"origin": "ATL", "destination": "YUL", "date": "2026-06-20"},
            ])
            returned = [*result["outbound_flights"], *result["return_flights"]]
            for group in result["multi_city_flights"]:
                returned.extend(group)
            self.assertEqual(self.state()["events"][0]["offers"], [eval_state.flight_evidence(f) for f in returned])

    def test_cancellation_removal_and_reset_are_visible(self):
        self.book(self.search("ATL", "BOS")["outbound_flights"][0])
        original = self.state()
        booking_store._bookings[0]["status"] = "cancelled"
        self.assertEqual(self.state()["bookings"][0]["status"], "cancelled")
        booking_store._bookings.clear()
        self.assertEqual(self.state()["bookings"], [])
        self.assertEqual(self.client.post("/api/reset").status_code, 200)
        state = self.state()
        self.assertEqual(state["events"], [])
        self.assertNotEqual(state["generation"], original["generation"])

    def test_bounded_history_exposes_truncation(self):
        with patch.object(eval_state, "MAX_EVENTS", 2):
            for _ in range(3):
                self.search()
        state = self.state()
        self.assertEqual(len(state["events"]), 2)
        self.assertIsInstance(state["discarded_through_ms"], int)


if __name__ == "__main__":
    unittest.main()
