"""Inspect only persisted Harbor artifacts after its failed-trial cleanup."""

import json
import sys
from pathlib import Path


def check(path, secret):
    root = Path(path)
    trials = [json.loads(p.read_text()) for p in root.glob("*/result.json")]
    assert len(trials) == 1, trials
    trial = trials[0]
    assert trial.get("exception_info"), trial
    assert not (trial.get("verifier_result") or {}).get("rewards"), trial
    results = list(root.glob("*/artifacts/**/webarena-service/result.json"))
    assert len(results) == 1, list(root.rglob("result.json"))
    diagnostics = results[0].parent
    result = json.loads(results[0].read_text())
    assert result["status"] == "setup_error" and result["exit_code"] == 1, result
    assert result["ready"] is False and result["graded"] is False, result
    assert "rewards" not in result and "FileNotFoundError" in result["error"], result
    stderr = (diagnostics / "stderr.log").read_text()
    assert "FileNotFoundError" in stderr and "missing?token=<redacted>" in stderr, stderr
    assert " in serve" in stderr, stderr
    for item in diagnostics.iterdir():
        if item.is_file():
            assert secret not in item.read_text(), item
    assert not (diagnostics / "ready.json").exists()
    print("Failed Harbor setup retained its redacted original error and exit status after cleanup.")


if __name__ == "__main__":
    check(sys.argv[1], sys.argv[2])
