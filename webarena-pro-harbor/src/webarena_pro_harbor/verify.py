"""Standalone verifier installed in Harbor's separate, minimal grader image."""

import json
import math
from pathlib import Path


def verify(
    source=Path("/webarena-evidence/result.json"), output=Path("/logs/verifier/reward.json")
):
    # No fallback reward: missing, incomplete, or erroneous evidence is a
    # verification error, never an ordinary zero-scoring benchmark attempt.
    result = json.loads(source.read_text())
    if result.get("schema_version") != 1 or result.get("status") != "graded":
        raise ValueError(
            "Core evaluation did not complete successfully: "
            + str(result.get("error", "missing or invalid completed result"))
        )
    rewards = result.get("rewards")
    if not isinstance(rewards, dict) or not {"reward", "success"} <= rewards.keys():
        raise ValueError("Missing Core reward/success metrics")
    for name, value in rewards.items():
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"Invalid metric: {name}")
    if rewards["success"] not in (0, 1) or rewards["success"] != int(rewards["reward"] == 1):
        raise ValueError("Core success and partial-credit reward disagree")
    if rewards["reward"] != result.get("score"):
        raise ValueError("Reward and Core score disagree")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rewards, allow_nan=False) + "\n")
    return rewards


if __name__ == "__main__":
    verify()
