"""Fail CI if Harbor itself succeeds but a smoke trial failed or lacked rewards."""

import json
import sys
from pathlib import Path


def check(path):
    usage = json.loads((Path(path) / "model_requests.json").read_text())
    assert usage["runner"] == "harbor" and usage["requests"] == []  # Oracle makes no model calls.
    trials = []
    for result_path in Path(path).glob("*/result.json"):
        result = json.loads(result_path.read_text())
        if "verifier_result" in result:
            trials.append(result)
    assert len(trials) == 2, f"Expected two trials, got {len(trials)}"
    for trial in trials:
        assert not trial.get("exception_info"), trial.get("exception_info")
        rewards = (trial.get("verifier_result") or {}).get("rewards")
        assert rewards and rewards["reward"] == rewards["success"] == 1, rewards
    print("Both isolated Harbor trials returned reward=1 and success=1.")


if __name__ == "__main__":
    check(sys.argv[1])
