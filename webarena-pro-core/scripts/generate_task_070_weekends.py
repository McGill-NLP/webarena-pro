"""Regenerate task 070's dates from Flight Search's clock before packaging Core."""

import argparse
import json
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from runpy import run_path

CORE = Path(__file__).resolve().parents[1]
CLOCK = CORE.parent / "websites/flight-search/backend/benchmark.py"
TASKS = CORE / "src/webarena_pro_core/config/flight-search.raw.json"


def update_weekends(task: dict, today: date) -> None:
    first_friday = today + timedelta(days=(4 - today.weekday()) % 7)
    fridays = (first_friday, first_friday + timedelta(weeks=1))
    windows = " or ".join(f"{day} through {day + timedelta(days=2)}" for day in fridays)
    departures = "|".join(
        (friday + timedelta(days=offset)).isoformat() for friday in fridays for offset in range(3)
    )

    task["intent"] = (
        f"Today is {today} in Flight Search. Book a flight from Toronto to Vancouver for next weekend."
    )
    rubric = (
        f"Using Flight Search's date of {today}, a flight from Toronto to Vancouver "
        f"was booked for next weekend, departing {windows} (inclusive)."
    )
    booking = next(node for node in task["eval"]["nodes"] if node["id"] == "r1")["eval_config"]
    booking["rubric"] = rubric
    strategies = {strategy["type"]: strategy["config"] for strategy in booking["strategies"]}
    strategies["llm_judge"]["rubric"] = rubric
    check = next(
        check for check in strategies["backend_state"]["checks"] if check["type"] == "body_regex"
    )
    check["pattern"] = (
        r'"outbound_flight":\s*\{[^}]*"origin":\s*"(?:YYZ|YTZ)"'
        r'[^}]*"destination":\s*"YVR"[^}]*"departure":\s*"'
        f"(?:{departures})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the packaged task is stale")
    args = parser.parse_args()
    tasks = json.loads(TASKS.read_text())
    task = next(task for task in tasks if task["task_id"] == "070")
    original_task = deepcopy(task)
    update_weekends(task, run_path(str(CLOCK))["BENCHMARK_DATE"])
    if task != original_task:
        if args.check:
            raise SystemExit(f"Task 070 is out of sync. Run {Path(__file__).name} to refresh it.")
        TASKS.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
