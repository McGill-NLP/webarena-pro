"""Task 070 uses the Flight Search calendar even in a November Harbor episode."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import requests
from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import EvalContext
from webarena_pro_core.eval.llm_judge import build_judge_messages

from webarena_pro_harbor.cli import select_tasks
from webarena_pro_harbor.export import export_tasks


def test_packaged_weekends_match_the_flight_search_clock():
    core = Path(__file__).resolve().parents[2] / "webarena-pro-core"
    generator = core / "scripts/generate_task_070_weekends.py"
    subprocess.run([sys.executable, generator, "--check"], check=True)


def test_task_070_in_a_november_episode(tmp_path, monkeypatch):
    export_tasks(select_tasks("test", "flight-search", "070"), tmp_path / "tasks", split="test")
    root = tmp_path / "tasks/webarena-pro-test-070"
    instruction = (root / "instruction.md").read_text()
    assert "Today is 2026-04-01 in Flight Search" in instruction

    task = json.loads((root / "environment/browser/episode.json").read_text())["task"]
    context = EvalContext(task_config=task, task_start_date=date(2026, 11, 26))
    booking = next(n for n in task["eval"]["nodes"] if n["id"] == "r1")["eval_config"]
    strategies = {s["type"]: s["config"] for s in booking["strategies"]}
    rubric = strategies["llm_judge"]["rubric"]
    assert "Flight Search's date of 2026-04-01" in rubric
    assert "2026-04-03 through 2026-04-05 or 2026-04-10 through 2026-04-12" in rubric
    messages = build_judge_messages(rubric, context)
    goal = messages["regular"][1]["content"][0]["text"]
    assert f"<rubric>\n{rubric}\n</rubric>" in goal
    assert "Task execution date: 2026-11-26" in goal

    reply = requests.Response()
    reply.status_code = 200
    evaluator = BackendStateEvaluator()
    monkeypatch.setattr(evaluator, "_send", lambda *_: reply)

    def passes(departure, origin="YYZ", destination="YVR"):
        flight = {"origin": origin, "destination": destination, "departure": f"{departure}T08:30:00"}
        reply._content = json.dumps([{"outbound_flight": flight}]).encode()
        result = evaluator.evaluate(strategies["backend_state"], context)
        assert not result.inconclusive, result.reason
        return result.passed

    for day in range(2, 14):
        expected = day in {3, 4, 5, 10, 11, 12}
        assert passes(date(2026, 4, day)) == expected, day
    assert passes("2026-04-11", origin="YTZ")
    assert not passes("2026-04-11", destination="YUL")
    assert not passes("2026-11-28")
    assert not passes("2026-12-05")
