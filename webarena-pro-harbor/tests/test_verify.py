import json

import pytest

from webarena_pro_harbor.verify import verify


def test_partial_credit_is_preserved(tmp_path):
    source, output = tmp_path / "result.json", tmp_path / "reward.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "graded",
                "score": 0.5,
                "rewards": {"reward": 0.5, "success": 0, "score_at_50": 0.5},
            }
        )
    )
    assert verify(source, output)["reward"] == 0.5
    assert json.loads(output.read_text())["success"] == 0


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"schema_version": 1, "status": "error"},
        {"schema_version": 1, "status": "graded", "rewards": {"reward": 0.5, "success": 1}},
        {
            "schema_version": 1,
            "status": "graded",
            "rewards": {"reward": float("nan"), "success": 0},
        },
        {"schema_version": 1, "status": "graded", "rewards": {"reward": True, "success": 1}},
        {
            "schema_version": 1,
            "status": "graded",
            "score": 1,
            "rewards": {"reward": 0.5, "success": 0},
        },
    ],
)
def test_invalid_evidence_never_becomes_zero(tmp_path, data):
    source, output = tmp_path / "result.json", tmp_path / "reward.json"
    source.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        verify(source, output)
    assert not output.exists()


def test_missing_evidence_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        verify(tmp_path / "missing", tmp_path / "reward.json")


def test_failed_grading_exposes_cause_without_inventing_reward(tmp_path):
    source, output = tmp_path / "result.json", tmp_path / "reward.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "error",
                "error": "TimeoutError: Core/browser supervisor timed out",
            }
        )
    )
    with pytest.raises(ValueError, match="Core/browser supervisor timed out"):
        verify(source, output)
    assert not output.exists()
