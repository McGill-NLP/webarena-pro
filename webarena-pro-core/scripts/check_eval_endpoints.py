#!/usr/bin/env python3
"""Read-only release gate for the four image-backed evaluator state APIs.

Run from a source checkout with Core available (see docs/source/evaluator-images.md).
The caller starts isolated containers and supplies an immutable image identity;
this command never starts, resets, changes, or stops any website.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import hashlib
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "webarena-pro-core/src/webarena_pro_core/config"
# Required keys are shared with current source routes. Extra fields are compatible.
# Every row is checked, including tables that a single representative task omits.
SCHEMAS = {
    "mydrive": {
        "users": "email username",
        "folders": "path name owner inTrash",
        "files": "path name size mimeType owner inTrash id ownerEmail",
        "shares": "type target sharedWith permission owner",
    },
    "yt-lite": {
        "videos": "id title channel views duration category description created_at",
        "likes": "video_id username value",
        "comments": "id video_id username text created_at",
        "watch_later": "username video_id",
        "history": "username video_id watched_at",
        "playlists": "id username name created_at",
        "playlist_videos": "playlist_id video_id",
        "users": "username created_at",
    },
    "notion": {
        "workspaces": "name slug",
        "database_pages": "workspace page db_count property_counts",
        "pages": "title icon type workspace parent created_by deleted published share_tokens",
        "blocks": "page workspace type text",
        "databases": "page workspace parent property_count properties rows",
    },
    "travelmap": {
        "bookings": "confirmation_code status guest listing check_in check_out guests",
        "wishlists": "user listing",
        "threads": "id listing guest host subject",
        "messages": "thread_id sender body",
        "blocked_dates": "listing date",
    },
}
SEED_TABLES = {"mydrive": "users", "yt-lite": "videos", "notion": "pages", "travelmap": "bookings"}


def contracts(config=CONFIG):
    """Reconcile active raw Test tasks and embedded Dev DAGs, including cross-site use."""
    splits = {
        "test": [task for path in sorted(config.glob("*.raw.json")) for task in json.loads(path.read_text())],
        "dev": json.loads((config / "splits/dev.json").read_text())["tasks"],
    }
    result = []
    for split, tasks in splits.items():
        for task in tasks:
            baselines = {b["name"]: b for b in task["eval"].get("baseline", [])}
            for node in task["eval"]["nodes"]:
                for index, strategy in enumerate(node.get("eval_config", {}).get("strategies", [])):
                    spec = strategy.get("config", {})
                    baseline = baselines.get(spec.get("baseline_ref"), {})
                    if baseline.get("provider") == "mydrive_files":
                        spec = {**spec, "site": baseline.get("params", {}).get("site", task["sites"][0]),
                                "api": "eval_state", "snapshot_provider": "mydrive_files"}
                    site = spec.get("site", task["sites"][0])
                    if site in SCHEMAS and spec.get("api") in {"eval_state", "eval_state_table"}:
                        result.append({"split": split, "task_id": task["task_id"], "node_id": node["id"],
                                       "strategy_index": index, "site": site, "api": spec["api"],
                                       "checks": spec.get("checks", []), "config": spec})
    return result


def inventory(entries):
    rows = []
    for split in ("test", "dev"):
        for site in SCHEMAS:
            selected = [entry for entry in entries if entry["split"] == split and entry["site"] == site]
            rows.append({"split": split, "site": site, "tasks": len({e["task_id"] for e in selected}),
                         "nodes": len({(e["task_id"], e["node_id"]) for e in selected}),
                         "strategies": len(selected), "checks": sum(len(e["checks"]) for e in selected),
                         "apis": dict(Counter(e["api"] for e in selected))})
    return rows


def validate_schema(site, payload):
    errors = []
    if not isinstance(payload, dict):
        return ["response must be a JSON object"]
    for table, required in SCHEMAS[site].items():
        rows = payload.get(table)
        if not isinstance(rows, list):
            errors.append(f"{table}: expected array")
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"{table}[{index}]: expected object")
                continue
            missing = set(required.split()) - row.keys()
            if missing:
                errors.append(f"{table}[{index}]: missing {','.join(sorted(missing))}")
            for key in ("inTrash", "deleted", "published"):
                if key in row and not isinstance(row[key], bool):
                    errors.append(f"{table}[{index}].{key}: expected boolean")
            for key in ("properties", "rows", "property_counts", "share_tokens"):
                if key in row and not isinstance(row[key], list):
                    errors.append(f"{table}[{index}].{key}: expected array")
    if site == "mydrive" and isinstance(payload.get("files"), list):
        from webarena_pro_core.eval.providers.mydrive import MyDriveFilesProvider
        try:
            MyDriveFilesProvider.from_payload(payload)
        except ValueError as error:
            errors.append(str(error))
        for index, row in enumerate(payload["files"]):
            if not isinstance(row, dict):
                continue
            text_file = (str(row.get("mimeType", "")).startswith("text/")
                         or re.search(r"\.(txt|md|csv|json|xml|html|css|js|ts|jsx|tsx|py|java|c|h|cpp|sh|bash|sql|yml|yaml)$", str(row.get("name", "")), re.I))
            size = row.get("size")
            if text_file and isinstance(size, int) and size <= 65536 and row.get("inTrash") is False:
                if not isinstance(row.get("content"), str):
                    errors.append(f"files[{index}].content: small active text files must include content")
    # A fresh release image must contain usable seed data, not just empty placeholders.
    if not payload.get(SEED_TABLES[site]):
        errors.append(f"{SEED_TABLES[site]}: seeded rows are missing")
    for index, database in enumerate(payload.get("databases", [])) if site == "notion" else []:
        if not isinstance(database, dict):
            continue
        for prop in database.get("properties", []) if isinstance(database.get("properties"), list) else []:
            if not isinstance(prop, dict) or not {"name", "type"} <= prop.keys():
                errors.append(f"databases[{index}].properties: expected name/type objects")
        for row in database.get("rows", []) if isinstance(database.get("rows"), list) else []:
            if not isinstance(row, dict) or "title" not in row or not isinstance(row.get("cells"), dict):
                errors.append(f"databases[{index}].rows: expected title/cells objects")
    return errors


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, token=None):
    headers = {"X-Eval-Token": token} if token else {}
    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.build_opener(NoRedirect).open(request, timeout=60)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.read()


def probe(site, base_url, token, entries, request=fetch):
    from webarena_pro_core.eval.api_registry import resolve_api_template
    from webarena_pro_core.eval.backend_state import BackendStateEvaluator
    import requests

    result = {"site": site, "errors": [], "authentication": {}, "checks": []}
    # Use the same registered URL and authentication contract as the evaluator.
    specs = [e["config"] for e in entries if e["site"] == site]
    if not specs:
        result["errors"].append("no active evaluator contracts found")
        return result
    urls = {}
    for spec in specs:
        resolved = resolve_api_template(site, spec["api"], spec.get("params", {}))
        if resolved.get("auth_mode") != "eval_token" or resolved.get("method", "GET") != "GET":
            result["errors"].append(f"{spec['api']}: expected token-gated GET")
            continue
        url = resolved["url"].replace(f"__{site.upper()}__", base_url.rstrip("/"))
        if "__" in url:
            result["errors"].append(f"{spec['api']}: unresolved URL placeholder")
            continue
        urls[url] = spec["api"]
    evaluator = BackendStateEvaluator()
    for url in urls:
        for mode, supplied in (("missing", None), ("incorrect", secrets.token_hex(32)), ("authenticated", token)):
            try:
                status, body = request(url, supplied)
            except Exception as error:
                result["errors"].append(f"{mode}: request failed ({type(error).__name__})")
                continue
            result["authentication"][mode] = status
            expected = 200 if mode == "authenticated" else 403
            if status != expected:
                result["errors"].append(f"{mode}: HTTP {status}, expected {expected}")
                continue
            if mode != "authenticated":
                continue
            try:
                payload = json.loads(body)
            except (ValueError, UnicodeDecodeError):
                result["errors"].append("authenticated: response is not JSON")
                continue
            result["errors"].extend(validate_schema(site, payload))
            if result["errors"]:
                continue
            result["rows"] = {table: len(payload[table]) for table in SCHEMAS[site]}
            response = requests.Response()
            response.status_code = status
            response._content = body
            # Exercise every current predicate against the real response. A false
            # task predicate is normal before an agent acts; an exception or an
            # unsupported check is an incompatible evaluator/image contract.
            for entry in (e for e in entries if e["site"] == site):
                for index, check in enumerate(entry["checks"]):
                    identity = {key: entry[key] for key in ("split", "task_id", "node_id", "strategy_index")}
                    identity["check_index"] = index
                    try:
                        if entry["config"].get("snapshot_provider") == "mydrive_files":
                            from webarena_pro_core.eval.providers.mydrive import MyDriveFilesProvider
                            snapshot = MyDriveFilesProvider.from_payload(payload)
                            passed, reason = evaluator._run_snapshot_check(
                                check, snapshot.diff(snapshot), snapshot, snapshot)
                        else:
                            passed, reason = evaluator._run_check(check, response)
                        if reason.startswith("unknown check type"):
                            raise ValueError(reason)
                        result["checks"].append({**identity, "passed": passed})
                    except Exception as error:
                        result["errors"].append(f"{entry['task_id']}/{entry['node_id']}/{index}: {type(error).__name__}")
            # The endpoint must also support a positive deterministic seed probe.
            passed, _ = evaluator._run_check({"type": "json_path", "path": SEED_TABLES[site],
                                             "operator": "length_gte", "value": 1}, response)
            result["seed_probe_passed"] = passed
            if not passed:
                result["errors"].append("deterministic seed probe failed")
    return result


def assignments(values):
    result = {}
    for value in values:
        site, separator, setting = value.partition("=")
        if not separator or site not in SCHEMAS or site in result or not setting:
            raise ValueError(f"expected one {','.join(SCHEMAS)}=VALUE per site")
        result[site] = setting
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", action="append", default=[], metavar="SITE=URL")
    parser.add_argument("--image", action="append", default=[], metavar="SITE=IMMUTABLE_IMAGE")
    parser.add_argument("--token-env", default="WP_EVAL_TOKEN", help="name of environment variable containing the test container token")
    parser.add_argument("--output", type=Path, help="write JSON evidence (no token or state body)")
    args = parser.parse_args(argv)
    try:
        sites, images = assignments(args.site), assignments(args.image)
        if sites.keys() != images.keys():
            raise ValueError("supply one immutable --image identity for every --site")
        if any(not re.fullmatch(r"(?:[A-Za-z0-9./:_-]+@)?sha256:[0-9a-f]{64}", value) for value in images.values()):
            raise ValueError("--image must be a digest reference or a local sha256 image ID, never a mutable tag")
        if sites and not os.environ.get(args.token_env):
            raise ValueError(f"{args.token_env} must contain the token used to start the isolated containers")
    except ValueError as error:
        parser.error(str(error))
    entries = contracts()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    inputs = [Path(__file__), *CONFIG.glob("*.raw.json"), CONFIG / "splits/dev.json",
              ROOT / "webarena-pro-core/src/webarena_pro_core/eval/api_registry.py",
              ROOT / "webarena-pro-core/src/webarena_pro_core/eval/backend_state.py",
              ROOT / "websites/mydrive/mydrive/src/app/api/eval/state/route.ts",
              ROOT / "websites/notion/app/api/eval/state/route.ts",
              ROOT / "websites/yt-lite/app.py", ROOT / "websites/travelmap/app/main.py",
              ROOT / "websites/mydrive/mydrive/Dockerfile",
              *(ROOT / "websites" / site / "Dockerfile" for site in ("notion", "yt-lite", "travelmap"))]
    hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    report = {"source_revision": revision, "source_dirty": dirty, "source_sha256": hashes,
              "inventory": inventory(entries), "sites": []}
    for site, url in sites.items():
        result = probe(site, url, os.environ[args.token_env], entries)
        result["image"] = images[site]
        report["sites"].append(result)
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded)
    return int(any(result["errors"] for result in report["sites"]))


if __name__ == "__main__":
    sys.exit(main())
