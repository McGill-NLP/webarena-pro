import pytest

from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import EvalContext
from webarena_pro_core.eval.snapshot import (
    Snapshot,
    SnapshotUnavailableError,
    build_snapshot_bundle,
)


@pytest.mark.parametrize("phase", ["baseline", "current", "both"])
@pytest.mark.parametrize(
    "check",
    [
        {"type": "snapshot_diff_added"},
        {"type": "snapshot_diff_removed"},
        {"type": "snapshot_diff_empty"},
        {"type": "snapshot_diff_count", "operator": "eq", "value": 0},
        {"type": "snapshot_diff_moved"},
        {"type": "snapshot_entry_attr", "scope": "current"},
    ],
)
def test_unavailable_snapshots_cannot_satisfy_checks(phase, check):
    baseline = Snapshot(entries={"file.txt": {"etag": "same"}})
    current = Snapshot(entries={"file.txt": {"etag": "same"}})
    if phase in {"baseline", "both"}:
        baseline = Snapshot(error="ConnectionError: baseline offline")
    if phase in {"current", "both"}:
        current = Snapshot(error="ConnectionError: current offline")

    with pytest.raises(SnapshotUnavailableError, match="snapshot unavailable"):
        baseline.diff(current)

    bundle = build_snapshot_bundle(baseline, current)
    assert bundle["diff"] is None
    result = BackendStateEvaluator().evaluate(
        {"baseline_ref": "files", "checks": [check]},
        EvalContext(baselines={"files": bundle}),
    )
    assert result.passed is False
    assert result.inconclusive is True
    assert "ConnectionError" in result.reason
    if phase in {"baseline", "both"}:
        assert "baseline snapshot unavailable" in result.reason
    if phase in {"current", "both"}:
        assert "current snapshot unavailable" in result.reason


@pytest.mark.parametrize(
    "baseline,current,check",
    [
        (Snapshot(), Snapshot(entries={"file.txt": {}}), "snapshot_diff_added"),
        (Snapshot(entries={"file.txt": {}}), Snapshot(), "snapshot_diff_removed"),
        (Snapshot(), Snapshot(), "snapshot_diff_empty"),
    ],
)
def test_successfully_empty_snapshots_remain_valid(baseline, current, check):
    bundle = build_snapshot_bundle(baseline, current)
    assert "error" not in bundle
    result = BackendStateEvaluator().evaluate(
        {"baseline_ref": "files", "checks": [{"type": check}]},
        EvalContext(baselines={"files": bundle}),
    )
    assert result.passed is True
    assert result.inconclusive is False


def test_snapshot_error_survives_json_round_trip():
    snapshot = Snapshot(error="ConnectionError: offline")
    restored = Snapshot.from_json(snapshot.to_json())

    assert restored.error == snapshot.error
    with pytest.raises(SnapshotUnavailableError):
        restored.diff(Snapshot())
    assert Snapshot().to_json() == {"entries": {}}
    assert Snapshot.from_json({"entries": {}}).error is None


def test_diff_still_detects_changed_and_unchanged_entries():
    baseline = Snapshot(entries={"changed": {"etag": "old"}, "same": {"etag": "same"}})
    current = Snapshot(entries={"changed": {"etag": "new"}, "same": {"etag": "same"}})

    diff = baseline.diff(current)

    assert diff.changed == ["changed"]
    assert diff.unchanged == ["same"]
    assert not diff.is_empty()
