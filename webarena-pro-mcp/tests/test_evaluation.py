from datetime import date
from types import SimpleNamespace

from webarena_pro_core.eval.snapshot import Snapshot
from webarena_pro_core.eval.ui_evidence import UIEvidence, UIEvidencePlan, UIProbe, UIProbeResult
from webarena_pro_mcp.evaluation import CoreEvaluator, ScoreBook


def evaluate(task, **kwargs):
    evaluator = CoreEvaluator(task, date(2026, 11, 5), 123456)
    evaluator.capture_baselines()
    return evaluator.evaluate(
        ui_evidence=kwargs.pop("ui_evidence", None),
        trajectory=[],
        observation={"url": "http://test", "axtree_txt": "test"},
        downloads=kwargs.pop("downloads", []),
        **kwargs,
    )


def test_final_answer_is_core_answer_match(task):
    assert evaluate(task, last_action="send_msg_to_user('42')")["score"] == 1
    assert evaluate(task, last_action="browser_type({'text': '42'})")["score"] == 0


def test_download_evidence(task, tmp_path):
    task.evaluation = {"nodes": [{"id": "download", "type": "file_downloaded", "eval_config": {"extension": ".csv"}}]}
    path = tmp_path / "report.csv"
    path.write_text("name,value\nx,42\n")
    assert (
        evaluate(task, last_action="click()", downloads=[{"path": str(path), "suggested_filename": path.name}])["score"]
        == 1
    )
    assert evaluate(task, last_action="click()", downloads=[])["score"] == 0


def test_serialized_ui_evidence_is_retained_and_bound_to_requested_step(task):
    probe = UIProbe(kind="count", selector=".saved")
    evidence = UIEvidence(
        evaluation_id="capture-5", step=5, tab_id="0", url="http://test",
        captured_at=1.0, status="ok", plan_sha256=UIEvidencePlan(probes=[probe]).sha256,
        results={probe.key: UIProbeResult(probe=probe, status="ok", count=1)},
    ).model_dump(mode="json")
    task.evaluation = {"nodes": [{"id": "ui", "type": "ui_state", "eval_config": {
        "checks": [{"method": "element_exists", "selector": ".saved"}],
    }}]}
    current = evaluate(task, ui_evidence=evidence, evaluation_step=5, last_action="click()")
    assert current["score"] == 1
    assert current["ui_evidence"] == evidence
    stale = evaluate(task, ui_evidence=evidence, evaluation_step=6, last_action="click()")
    assert stale["score"] == 0
    assert stale["dag_results"]["ui"]["reason"] == "UI capture step mismatch"


def test_backend_baseline_change_and_missing_evidence(task, monkeypatch):
    task.evaluation = {
        "baseline": [{"name": "items", "provider": "fixture"}],
        "nodes": [
            {
                "id": "added",
                "type": "backend_state",
                "eval_config": {
                    "baseline_ref": "items",
                    "checks": [{"type": "snapshot_diff_added", "min_count": 1}],
                },
            }
        ],
    }
    baseline = Snapshot(entries={"old": {"etag": "1"}})
    current = Snapshot(entries={"old": {"etag": "1"}, "new": {"etag": "1"}})
    snapshots = iter([baseline, current])
    monkeypatch.setattr(
        "webarena_pro_mcp.evaluation.get_provider", lambda _: SimpleNamespace(fetch=lambda *_: next(snapshots))
    )
    result = evaluate(task, last_action="click()")
    assert result["score"] == 1, result

    def fail(*_):
        raise ConnectionError("fixture unavailable")

    monkeypatch.setattr("webarena_pro_mcp.evaluation.get_provider", lambda _: SimpleNamespace(fetch=fail))
    missing = evaluate(task, last_action="click()")
    assert missing["score"] == 0
    assert "unavailable" in missing["dag_results"]["added"]["reason"]


def test_cutoffs_preserve_actual_score_and_terminal_provenance():
    book = ScoreBook(-1)
    book.record(50, {"score": 1.0, "success": True})
    book.record(100, {"score": 0.5, "success": False})
    summary = book.finish("browser_disconnected")
    assert summary["success"] is None
    assert summary["step_budget_scores"]["50"]["success"] is True
    assert summary["step_budget_scores"]["100"]["score"] == 0.5
    assert summary["step_budget_scores"]["unlimited"]["status"] == "unavailable"


def test_early_terminal_supplies_only_applicable_cutoffs():
    for limit, keys in [(50, {"50"}), (100, {"50", "100"}), (-1, {"50", "100", "unlimited"})]:
        book = ScoreBook(limit)
        book.record(3, {"score": 0.25, "success": False}, terminal=True)
        summary = book.finish("done")
        assert set(summary["step_budget_scores"]) == keys
        assert all(entry["evaluated_at_step"] == 3 for entry in summary["step_budget_scores"].values())
