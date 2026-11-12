"""Structured backend assertions must not combine records or trust partial pages."""
import copy
import json
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import EvalContext


def response(payload, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    return result


def config():
    return {
        "url": "https://service.example/items?active=true",
        "resolve": [{"url": "https://service.example/me", "extract": "id", "bind": "owner"}],
        "pagination": {"path": "data.items", "page_size": 1, "max_pages": 3},
        "checks": [{
            "type": "json_collection_contains", "path": "data.items",
            "match": {"owner_id": {"resolved": "owner"}, "deleted": False},
            "created_since_task_start": "created_at",
            "text": {"field": "description", "contains_all": ["release notes", "version two"],
                     "link_targets_any": ["https://docs.example/releases/2"]},
        }],
    }


def item(**changes):
    return {"id": "new", "owner_id": "user", "deleted": False, "created_at": 100,
            "description": "RELEASE—NOTES: version two [read](https://docs.example/releases/2)", **changes}


@pytest.mark.parametrize("as_dict", [False, True])
def test_complete_collection_rechecks_current_records_and_preserves_query(monkeypatch, as_dict):
    evaluator = BackendStateEvaluator()
    records = [item(id="old", created_at=99), item()]
    calls = []

    def send(spec, context):
        if spec["url"].endswith("/me"):
            return response({"id": "user"})
        query = parse_qs(urlsplit(spec["url"]).query)
        assert query["active"] == ["true"] and query["per_page"] == ["1"]
        page = int(query["page"][0])
        calls.append(page)
        rows = records[page:page + 1]
        return response({"data": {"items": {row["id"]: row for row in rows} if as_dict else rows}})

    monkeypatch.setattr(evaluator, "_send", send)
    context = EvalContext(task_start_time_ms=100)
    result = evaluator.evaluate(config(), context)
    assert result.passed and not result.inconclusive
    assert "matched_ids=['new']" in result.reason and "evidence_sha256=" in result.reason
    assert calls == [0, 1, 2]
    records[1]["deleted"] = True
    result = evaluator.evaluate(config(), context)
    assert not result.passed and not result.inconclusive


@pytest.mark.parametrize("change", [
    {"owner_id": "someone-else"}, {"created_at": 99}, {"deleted": True},
    {"description": "release notes version two [https://docs.example/releases/2](https://wrong.example)"},
    {"description": "release notes version two https://docs.example/releases/2?different=1"},
])
def test_record_filters_and_exact_link_failure_are_definitive(monkeypatch, change):
    evaluator = BackendStateEvaluator()
    cfg = config()
    cfg.pop("pagination")
    monkeypatch.setattr(evaluator, "_send", lambda spec, ctx: response(
        {"id": "user"} if spec["url"].endswith("/me") else {"data": {"items": [item(**change)]}}
    ))
    result = evaluator.evaluate(cfg, EvalContext(task_start_time_ms=100))
    assert not result.passed and not result.inconclusive


def test_text_requirements_cannot_be_combined_across_records(monkeypatch):
    evaluator = BackendStateEvaluator()
    cfg = config()
    cfg.pop("pagination")
    records = [item(description="release notes version two"),
               item(id="link", description="https://docs.example/releases/2")]
    monkeypatch.setattr(evaluator, "_send", lambda spec, ctx: response(
        {"id": "user"} if spec["url"].endswith("/me") else {"data": {"items": records}}
    ))
    result = evaluator.evaluate(cfg, EvalContext(task_start_time_ms=100))
    assert not result.passed and not result.inconclusive


@pytest.mark.parametrize("failure", ["http", "malformed", "limit", "changed_type"])
def test_incomplete_pagination_never_passes_on_an_earlier_matching_record(monkeypatch, failure):
    evaluator = BackendStateEvaluator()

    def send(spec, context):
        if spec["url"].endswith("/me"):
            return response({"id": "user"})
        page = int(parse_qs(urlsplit(spec["url"]).query)["page"][0])
        if page and failure == "http":
            return response({}, 503)
        if page and failure == "malformed":
            return response({"data": {"items": None}})
        if page and failure == "changed_type":
            return response({"data": {"items": {}}})
        return response({"data": {"items": [item()]}})

    monkeypatch.setattr(evaluator, "_send", send)
    result = evaluator.evaluate(config(), EvalContext(task_start_time_ms=100))
    assert not result.passed and result.inconclusive


@pytest.mark.parametrize("failure", ["timestamp", "text", "collection", "record", "missing_start", "unknown_url"])
def test_unusable_collection_evidence_is_inconclusive(monkeypatch, failure):
    evaluator = BackendStateEvaluator()
    cfg = config()
    cfg.pop("pagination")
    records = [item()]
    context = EvalContext(task_start_time_ms=100)
    if failure == "timestamp":
        records[0]["created_at"] = "100"
    elif failure == "text":
        records[0]["description"] = None
    elif failure == "collection":
        records = None
    elif failure == "record":
        records = ["not an object"]
    elif failure == "missing_start":
        context.task_start_time_ms = None
    else:
        cfg["checks"][0]["text"]["link_targets_any"] = ["__UNKNOWN-SITE__/release"]
    monkeypatch.setattr(evaluator, "_send", lambda spec, ctx: response(
        {"id": "user"} if spec["url"].endswith("/me") else {"data": {"items": records}}
    ))
    result = evaluator.evaluate(cfg, context)
    assert not result.passed and result.inconclusive


@pytest.mark.parametrize("status,deleted,inconclusive", [(200, True, False), (403, False, True)])
def test_resolve_prerequisite_failure_stops_before_collection_request(monkeypatch, status, deleted, inconclusive):
    evaluator = BackendStateEvaluator()
    cfg = config()
    cfg["resolve"][0]["checks"] = [{"type": "json_path", "path": "deleted", "value": False}]
    calls = []

    def send(spec, context):
        calls.append(spec["url"])
        return response({"id": "user", "deleted": deleted}, status)

    monkeypatch.setattr(evaluator, "_send", send)
    result = evaluator.evaluate(cfg, EvalContext(task_start_time_ms=100))
    assert not result.passed and result.inconclusive == inconclusive
    assert calls == ["https://service.example/me"]


def test_unpaginated_requests_keep_existing_response_text_and_url(monkeypatch):
    evaluator = BackendStateEvaluator()
    original = response({"message": "unchanged"})
    cfg = {"url": "https://service.example/plain", "checks": [{"type": "body_contains", "value": original.text}]}
    calls = []

    def send(spec, context):
        calls.append(copy.deepcopy(spec))
        return original

    monkeypatch.setattr(evaluator, "_send", send)
    assert evaluator.evaluate(cfg, EvalContext()).passed
    assert len(calls) == 1 and calls[0]["url"] == cfg["url"]
