"""Task 092 grades deletion and preservation independently of the UI route."""
import json
from pathlib import Path

import pytest
import requests

from webarena_pro_core.eval import llm_judge
from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
from webarena_pro_core.eval.providers import get_provider
from webarena_pro_core.eval.snapshot import Snapshot, build_snapshot_bundle
from webarena_pro_core.task import WebArenaProTaskConfig

CONFIG = Path(__file__).parents[1] / "src/webarena_pro_core/config"
TASK = next(t for t in json.loads((CONFIG / "immich.raw.json").read_text()) if t["task_id"] == "092")


def response(body, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode()
    return result


def photo(asset_id, year=2014):
    return {"id": asset_id, "type": "IMAGE", "isTrashed": False,
            "localDateTime": f"{year}-04-01T12:00:00", "checksum": asset_id}


def listing(items, next_page=None):
    return {"assets": {"items": items, "count": len(items), "total": len(items), "nextPage": next_page}}


def test_provider_paginates_and_uses_authenticated_native_template(monkeypatch):
    seen = []
    pages = [listing([photo("keep-a"), photo("delete", 2015)], "2"), listing([photo("keep-b")])]
    def send(self, spec, context):
        seen.append(spec)
        return response(pages[len(seen) - 1])
    monkeypatch.setattr(BackendStateEvaluator, "_send", send)
    snapshot = get_provider("immich_assets").fetch("immich", {"exclude_year": 2015})
    assert set(snapshot.entries) == {"keep-a", "keep-b"}
    assert [json.loads(s["body"])["page"] for s in seen] == [1, 2]
    assert all(s["url"] == "__IMMICH__/api/search/metadata" and s["auth_mode"] == "bearer_login" for s in seen)


@pytest.mark.parametrize("pages,status", [
    ([{"error": "unauthorized"}], 401),
    ([{"error": "server failure"}], 500),
    ([{}], 200),
    ([{"assets": {"items": [], "count": 1, "total": 1, "nextPage": None}}], 200),
    ([{"assets": {"items": [], "count": 0, "total": 0}}], 200),
    ([listing([], "2")], 200),
    ([listing([photo("a")], "1")], 200),
    ([listing([photo("a")], "2"), listing([photo("a")])], 200),
    ([listing([{"id": "missing-date", "type": "IMAGE", "isTrashed": False}])], 200),
])
def test_provider_rejects_failed_partial_or_malformed_evidence(monkeypatch, pages, status):
    pending = iter(pages)
    monkeypatch.setattr(BackendStateEvaluator, "_send", lambda *args: response(next(pending), status))
    with pytest.raises((ValueError, requests.HTTPError)):
        get_provider("immich_assets").fetch("immich", {"exclude_year": 2015})


def test_later_page_failure_does_not_return_partial_snapshot(monkeypatch):
    replies = iter([response(listing([photo("a")], "2")), response({}, 503)])
    monkeypatch.setattr(BackendStateEvaluator, "_send", lambda *args: next(replies))
    with pytest.raises(requests.HTTPError):
        get_provider("immich_assets").fetch("immich", {})


@pytest.mark.parametrize("route", ["timeline selection", "date-filter search"])
@pytest.mark.parametrize("library,trash,current,expected", [
    (0, 0, ("a", "b"), (True, True, True, True)),
    (1, 0, ("a", "b"), (True, False, False, True)),
    (0, 1, ("a", "b"), (True, True, False, True)),
    (0, 0, ("a", "replacement"), (True, True, True, False)),
    (0, 0, ("a",), (True, True, True, False)),
])
def test_real_dag_rejects_incomplete_deletion_pending_trash_and_replacement(monkeypatch, route, library, trash, current, expected):
    def send(self, spec, context):
        body = json.loads(spec["body"])
        assert body["takenAfter"].startswith("2015-01-01")
        assert body["takenBefore"].startswith("2015-12-31")
        count = trash if "trashedAfter" in body else library
        return response(listing([photo(str(i), 2015) for i in range(count)]))
    monkeypatch.setattr(BackendStateEvaluator, "_send", send)
    calls = []
    def judge(rubric, context, model):
        calls.append(rubric)
        assert rubric == TASK["eval"]["nodes"][0]["eval_config"]["rubric"]
        assert "timeline" in rubric and "date-filter search is not required" in rubric
        return "pass", "Semantic route accepted by test hook"
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    baseline = Snapshot(entries={k: {"etag": k} for k in ("a", "b")})
    now = Snapshot(entries={k: {"etag": k} for k in current})
    context = EvalContext(task_config=TASK, last_action=route,
                          baselines={"other_photos": build_snapshot_bundle(baseline, now)})
    score, results = DAGEvaluator(parse_eval_dag(TASK["eval"])).evaluate(context)
    assert tuple(results[f"r{i}"]["passed"] for i in range(1, 5)) == expected
    assert score == pytest.approx(sum(expected) / len(expected))
    assert len(calls) == 1  # Known T0 failures never reach a permissive judge.


def test_missing_baseline_cannot_prove_preservation(monkeypatch):
    node = TASK["eval"]["nodes"][3]
    context = EvalContext(task_config=TASK)
    probe = BackendStateEvaluator().evaluate(node["eval_config"]["strategies"][0]["config"], context)
    assert not probe.passed
    assert probe.inconclusive
    assert "unknown baseline_ref" in probe.reason

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", lambda *args: pytest.fail("Missing baseline must not reach a judge"))
    score, results = DAGEvaluator(parse_eval_dag({"nodes": [node]})).evaluate(context)
    assert not results["r4"]["passed"]
    assert score == 0.0
    assert "T0:backend_state=INCONCLUSIVE(unknown baseline_ref" in results["r4"]["reason"]
    assert "llm_judge" not in results["r4"]["reason"]


@pytest.mark.parametrize("unavailable", ["baseline", "current", "both", "diff"])
def test_unavailable_snapshot_evidence_cannot_prove_preservation(monkeypatch, unavailable):
    baseline = Snapshot(entries={"original": {"etag": "original"}})
    current = Snapshot(entries={"original": {"etag": "original"}})
    if unavailable in {"baseline", "both"}:
        baseline = Snapshot(error="baseline fetch failed")
    if unavailable in {"current", "both"}:
        current = Snapshot(error="current fetch failed")
    bundle = build_snapshot_bundle(baseline, current)
    if unavailable == "diff":
        bundle["diff"] = None

    node = TASK["eval"]["nodes"][3]
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", lambda *args: pytest.fail("Unavailable snapshots must not reach a judge"))
    context = EvalContext(task_config=TASK, baselines={"other_photos": bundle})
    score, results = DAGEvaluator(parse_eval_dag({"nodes": [node]})).evaluate(context)

    assert score == 0.0
    assert not results["r4"]["passed"]
    assert "INCONCLUSIVE" in results["r4"]["reason"]
    assert "llm_judge" not in results["r4"]["reason"]


def test_task_identity_graph_and_split_unchanged():
    WebArenaProTaskConfig.from_raw_task(TASK, container_name="immich-deletion-test")
    assert TASK["intent"] == "Permanently delete all photos from 2015."
    assert [(n["id"], n.get("depends_on", [])) for n in TASK["eval"]["nodes"]] == [
        ("r1", []), ("r2", []), ("r3", ["r2"]), ("r4", [])]
    assert sum(t["task_id"] == "092" for p in CONFIG.glob("*.raw.json") for t in json.loads(p.read_text())) == 1
    assert not any(t["task_id"] == "092" for t in json.loads((CONFIG / "splits/dev.json").read_text())["tasks"])
