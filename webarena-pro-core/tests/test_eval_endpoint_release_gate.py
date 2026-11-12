"""The release gate rejects stale images, unprotected APIs and schema drift."""
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / "scripts/check_eval_endpoints.py"
SPEC = importlib.util.spec_from_file_location("check_eval_endpoints", PATH)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def seeded_payload(site):
    result = {table: [] for table in gate.SCHEMAS[site]}
    if site == "mydrive":
        result["fileSnapshotVersion"] = 1
    table = gate.SEED_TABLES[site]
    result[table] = [{field: "seed" for field in gate.SCHEMAS[site][table].split()}]
    for row in result[table]:
        for field in ("deleted", "published"):
            if field in row:
                row[field] = False
        if "share_tokens" in row:
            row["share_tokens"] = []
    return result


@pytest.mark.parametrize("site", gate.SCHEMAS)
def test_gate_accepts_authenticated_compatible_seed_and_runs_all_active_predicates(site):
    payload = seeded_payload(site)
    entries = gate.contracts()
    seen = []
    def request(url, token):
        seen.append((url, token))
        return (200, json.dumps(payload).encode()) if token == "private-token" else (403, b'{}')
    report = gate.probe(site, "http://127.0.0.1:12345", "private-token", entries, request)
    assert report["errors"] == []
    assert report["seed_probe_passed"]
    assert report["authentication"] == {"missing": 403, "incorrect": 403, "authenticated": 200}
    assert len(report["checks"]) == sum(len(e["checks"]) for e in entries if e["site"] == site)
    assert all(url == "http://127.0.0.1:12345/api/eval/state" for url, _ in seen)
    assert "private-token" not in json.dumps(report)


@pytest.mark.parametrize("status", [200, 302, 401, 404, 500])
def test_gate_rejects_wrong_negative_auth_status(status):
    def request(url, token):
        return ((200, json.dumps(seeded_payload("mydrive")).encode()) if token == "token"
                else (status, b'{}'))
    report = gate.probe("mydrive", "http://127.0.0.1:1", "token", gate.contracts(), request)
    assert report["errors"]


@pytest.mark.parametrize("body", [b'<html>login</html>', b'[]', b'{}', b'{"users":[]}'])
def test_gate_rejects_success_status_with_an_incompatible_body(body):
    def request(url, token):
        return (200, body) if token == "token" else (403, b'{}')
    report = gate.probe("mydrive", "http://127.0.0.1:1", "token", gate.contracts(), request)
    assert report["errors"]
    assert report["checks"] == []


@pytest.mark.parametrize("site", gate.SCHEMAS)
def test_gate_rejects_missing_tables_and_missing_row_fields(site):
    valid = seeded_payload(site)
    assert gate.validate_schema(site, valid) == []
    table = gate.SEED_TABLES[site]
    del valid[table][0][next(iter(valid[table][0]))]
    assert gate.validate_schema(site, valid)
    del valid[table]
    assert gate.validate_schema(site, valid)


def test_reconciled_inventory_includes_cross_site_and_dev_dags():
    entries = gate.contracts()
    assert len(entries) == 164
    creation = next(entry for entry in entries if entry["task_id"] == "310")
    assert creation["site"] == "mydrive"
    assert creation["config"]["snapshot_provider"] == "mydrive_files"
    assert creation["checks"][0]["type"] == "snapshot_diff_added"
    rows = {(r["split"], r["site"]): r for r in gate.inventory(entries)}
    assert [rows["test", site]["nodes"] for site in gate.SCHEMAS] == [35, 47, 39, 17]
    assert [rows["dev", site]["nodes"] for site in gate.SCHEMAS] == [9, 5, 1, 5]
    assert all(entry["api"] == "eval_state" for entry in entries)


def test_gate_rejects_mutable_image_tags():
    with pytest.raises(SystemExit) as error:
        gate.main(["--site", "mydrive=http://127.0.0.1:1", "--image", "mydrive=webarenapro/mydrive:latest"])
    assert error.value.code == 2
