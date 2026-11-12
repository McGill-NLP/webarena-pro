"""Keep the flight count tasks tied to the shipped route data and flight generator."""

import json
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import benchmark, main


CONFIG = Path(__file__).resolve().parents[3] / "webarena-pro-core/src/webarena_pro_core/config"
TASK_ID = "401"
INTENT = (
    "Set the displayed currency to USD. How many one-way economy flights from "
    "San Francisco (SFO) to Seattle (SEA) on 2026-06-15 are priced at $125 or less?"
)
QUERY = {
    "trip_type": "one_way",
    "legs": [{"origin": "SFO", "destination": "SEA", "date": "2026-06-15"}],
    "passengers": {"adults": 1, "children": 0, "infants": 0},
    "cabin_class": "economy",
    "filters": {},
    "sort_by": "cheapest",
}


class Task401FixtureTests(unittest.TestCase):
    def setUp(self):
        # Exercise the same fixed clock as BENCHMARK_PASSCODE=1 regardless of
        # the host date or the environment in which the tests are invoked.
        for module in (benchmark, main):
            self.enterContext(patch.object(module, "BENCHMARK_MODE", True))
        self.client = self.enterContext(TestClient(main.app))
        response = self.client.post("/api/auth/verify", json={"passkey": "flyingagents"})
        self.assertEqual(response.status_code, 200)

    def search(self, **filters):
        query = deepcopy(QUERY)
        query["filters"] = filters
        response = self.client.post("/api/search", json=query)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["outbound_flights"]

    def test_seeded_search_price_boundary_and_stops(self):
        self.assertEqual(benchmark.today(), date(2026, 4, 1))
        self.assertEqual(self.client.get("/api/config").json(), {
            "benchmark_mode": True, "benchmark_date": "2026-04-01",
        })
        offers = self.search()
        self.assertEqual([f["price_usd"] for f in offers],
                         [118, 120, 124, 125, 131, 136, 138, 139, 141])
        matching = self.search(max_price=125)
        self.assertEqual(matching, [f for f in offers if f["price_usd"] <= 125])
        self.assertEqual([(f["price_usd"], f["stops"]) for f in matching],
                         [(118, 0), (120, 0), (124, 1), (125, 0)])
        # Both common misreadings yield three, but exclude different offers.
        self.assertEqual([f["price_usd"] for f in self.search(max_price=124)],
                         [118, 120, 124])
        self.assertEqual([f["price_usd"] for f in self.search(max_price=125, max_stops=0)],
                         [118, 120, 125])

    def test_task_073_accepts_the_same_count_without_a_price_filter(self):
        raw = json.loads((CONFIG / "flight-search.raw.json").read_text())
        task = next(t for t in raw if t["task_id"] == "073")
        self.assertEqual(task["intent"],
                         "How many one-way economy flights from San Francisco (SFO) "
                         "to Seattle (SEA) on 2026-06-15 are priced at $125 or less?")
        # Read-only inspection and applying the optional control produce the
        # same inclusive USD result set, including its connecting itinerary.
        manually_counted = [f for f in self.search() if f["price_usd"] <= 125]
        self.assertEqual(manually_counted, self.search(max_price=125))
        self.assertEqual(len(manually_counted), 4)
        self.assertEqual(len([f for f in manually_counted if f["price_usd"] < 125]), 3)
        self.assertEqual(len([f for f in manually_counted if f["stops"] == 0]), 3)
        # The API uses USD; convert the display-currency limit just as the UI
        # does. The rubric accepts 0 for a consistent default-KRW answer.
        response = self.client.get("/api/currency/rates")
        self.assertEqual(response.status_code, 200)
        krw_rate = response.json()["rates"]["KRW"]
        self.assertEqual(self.search(max_price=125 / krw_rate), [])
        dag = task["eval"]
        self.assertEqual(dag["scoring"], "partial")
        self.assertEqual([(n["id"], n["depends_on"]) for n in dag["nodes"]],
                         [("r1", [])])
        config = dag["nodes"][0]["eval_config"]
        self.assertEqual(len(config["strategies"]), 1)
        judge = config["strategies"][0]
        self.assertEqual(judge["type"], "llm_judge")
        self.assertEqual(config["rubric"], judge["config"]["rubric"])
        for requirement in ("correct count depends on the display currency",
                            "in USD there are 4 flights at $125 or less (cheapest $118)",
                            "Seoul -> KRW) a 125 filter yields 0",
                            "Accept 4 with USD or 0 if the agent used the default currency "
                            "and says so consistently", "fail any other number"):
            self.assertIn(requirement, config["rubric"])
        self.assertNotIn("applied a max-price filter", config["rubric"])

    def test_dev_rubrics_match_generated_count(self):
        raw = json.loads((CONFIG / "flight-search.raw.json").read_text())
        self.assertFalse(any(t["task_id"] == TASK_ID for t in raw))
        dev = json.loads((CONFIG / "splits/dev.json").read_text())
        task = next(t for t in dev["tasks"] if t["task_id"] == TASK_ID)
        self.assertEqual(task["task_id"], "401")
        self.assertEqual(task["intent"], INTENT)

        dag = task["eval"]
        self.assertNotIn("intent", dag)
        self.assertEqual(len(dag["nodes"]), 1)
        count = len(self.search(max_price=125))
        criterion = f"Correct if the answer gives the filtered result count of {count}."
        config = dag["nodes"][0]["eval_config"]
        self.assertEqual(config["rubric"], criterion)
        # Keep contextual judging: answers need not use an exact output string.
        self.assertEqual(len(config["strategies"]), 1)
        judge = config["strategies"][0]
        self.assertEqual(judge["type"], "llm_judge")
        self.assertIn(f"Criterion: {criterion}\n", judge["config"]["rubric"])
        self.assertIn(f"Source reference answer (context): {count} flights.\n",
                      judge["config"]["rubric"])

        sampled = next(row for row in dev["sampling"]["sampled"]
                       if row["packaged_task_id"] == TASK_ID)
        source_eval = sampled["source_eval"]
        self.assertEqual(source_eval["rubrics"][0]["text"], criterion)
        self.assertEqual(source_eval["reference_answers"]["exact_match"], f"{count} flights.")
        self.assertEqual(source_eval["reference_answer_raw_annotation"], f"{count} flights.")


if __name__ == "__main__":
    unittest.main()
