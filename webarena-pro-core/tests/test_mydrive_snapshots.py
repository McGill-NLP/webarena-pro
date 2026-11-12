"""File identity, ownership and unavailable evidence in MyDrive creation checks."""

import json
from pathlib import Path

import pytest
import requests

from webarena_pro_core.eval.dag import EvalContext, NodeResult, get_node_evaluator
from webarena_pro_core.eval.providers import get_provider
from webarena_pro_core.eval.providers.mydrive import MyDriveFilesProvider
from webarena_pro_core.eval.snapshot import Snapshot, build_snapshot_bundle
from webarena_pro_core.eval.tiered import TieredRubricEvaluator


def file(file_id="new", **attrs):
    return {"id": file_id, "name": "Notes.doc", "path": "Notes.doc",
            "ownerEmail": "agent1@test.com", "inTrash": False,
            "mimeType": "application/vnd.google-apps.document", **attrs}


def payload(*files):
    return {"fileSnapshotVersion": 1, "files": list(files)}


def snapshot(*files):
    return MyDriveFilesProvider.from_payload(payload(*files))


@pytest.fixture
def creation_config():
    path = Path(__file__).parents[1] / "src/webarena_pro_core/config/acidwave.raw.json"
    task = next(t for t in json.loads(path.read_text()) if t["task_id"] == "310")
    return task["eval"]["nodes"][0]["eval_config"]


@pytest.fixture
def judge(monkeypatch):
    calls = []
    def evaluate(config, context):
        calls.append(config)
        return NodeResult(passed=True, reason="fallback")
    monkeypatch.setattr(get_node_evaluator("llm_judge"), "evaluate", evaluate)
    return calls


def grade(config, baseline, current):
    return TieredRubricEvaluator().evaluate(config, EvalContext(baselines={
        "mydrive_files": build_snapshot_bundle(baseline, current)}))


@pytest.mark.parametrize("name", ["Notes.doc", "Any title", "研究.md"])
@pytest.mark.parametrize("mime_type", ["application/vnd.google-apps.document", "application/json",
                                      "text/plain; charset=utf-8", "application/pdf"])
def test_new_saved_document_passes_without_name_matching(creation_config, judge, name, mime_type):
    result = grade(creation_config, snapshot(file("old")),
                   snapshot(file("old"), file(name=name, path=name, mimeType=mime_type)))
    assert result.passed
    assert "decided_by=T0:backend_state" in result.reason
    assert not judge


@pytest.mark.parametrize("before,after", [
    ([file()], [file()]),
    ([file()], [file(name="Renamed.doc", path="Renamed.doc")]),
    ([file()], [file(path="subfolder/Notes.doc")]),
    ([file(inTrash=True)], [file()]),
    ([file(ownerEmail="agent2@test.com")], [file()]),
    ([], []),
    ([], [file(ownerEmail="agent2@test.com")]),
    ([], [file(inTrash=True)]),
    ([], [file(mimeType="image/png")]),
])
def test_existing_restored_moved_or_ineligible_files_do_not_pass(creation_config, judge, before, after):
    result = grade(creation_config, snapshot(*before), snapshot(*after))
    assert not result.passed
    assert "decided_by=T0:backend_state" in result.reason
    assert not judge  # A definitive failure cannot be overturned by the judge.


@pytest.mark.parametrize("phase", ["baseline", "current", "missing"])
def test_unavailable_evidence_falls_back(creation_config, judge, phase):
    if phase == "missing":
        result = TieredRubricEvaluator().evaluate(creation_config, EvalContext())
    else:
        baseline = Snapshot(error="offline") if phase == "baseline" else snapshot()
        current = Snapshot(error="offline") if phase == "current" else snapshot(file())
        result = grade(creation_config, baseline, current)
    assert result.passed
    assert len(judge) == 1
    assert "INCONCLUSIVE" in result.reason


@pytest.mark.parametrize("body", [
    {}, {"files": []}, {"fileSnapshotVersion": 1},
    payload(None), payload({}), payload(file(id="")),
    payload(file(ownerEmail="")), payload(file(mimeType=None)),
    payload(file(inTrash="false")), payload(file(), file()),
])
def test_stale_and_malformed_responses_are_unavailable(body):
    with pytest.raises(ValueError):
        MyDriveFilesProvider.from_payload(body)


def test_empty_snapshot_and_json_round_trip():
    assert not snapshot().entries
    before = Snapshot.from_json(snapshot(file()).to_json())
    assert before.diff(snapshot(file(), file("another"))).added == ["another"]


@pytest.mark.parametrize("status", [200, 302, 401, 403, 404, 500])
def test_cross_site_fetch_uses_worker_url_and_shared_token(monkeypatch, status):
    monkeypatch.setenv("WP_MYDRIVE_URL", "http://worker.example:1234")
    monkeypatch.setenv("WP_ACIDWAVE_URL", "http://wrong.example:9999")
    monkeypatch.setenv("WP_EVAL_TOKEN", "private-test-token")
    def get(url, **kwargs):
        assert url == "http://worker.example:1234/api/eval/state"
        assert kwargs == {"headers": {"X-Eval-Token": "private-test-token"},
                          "timeout": 30, "allow_redirects": False}
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(payload(file())).encode()
        return response
    monkeypatch.setattr(requests, "get", get)
    provider = get_provider("mydrive_files")
    if status == 200:
        assert set(provider.fetch("acidwave", {"site": "mydrive"}).entries) == {"new"}
    else:
        with pytest.raises(ValueError, match=f"HTTP {status}"):
            provider.fetch("acidwave", {"site": "mydrive"})
