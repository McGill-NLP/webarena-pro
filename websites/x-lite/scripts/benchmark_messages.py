#!/usr/bin/env python3
"""Measure /messages with real BrowserGym extractors against an existing seeded DB.

Requires Flask, Playwright (with Chromium installed), and browsergym-core.
Use --app-dir for an older checkout to compare it against the same --database.
This does not initialize/reset the database or run the benchmark task runner.
"""

import argparse
import importlib.metadata
import importlib.util
import json
import logging
from pathlib import Path
import sqlite3
import sys
import threading
from time import perf_counter

from browsergym.core.observation import _pre_extract, extract_dom_snapshot, extract_merged_axtree
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--username", default="techvalueinvestor")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("--database must be an existing seeded SQLite database")

    spec = importlib.util.spec_from_file_location("x_lite_benchmark_app", args.app_dir / "app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.DB_PATH = str(args.database.resolve())
    with sqlite3.connect(module.DB_PATH) as db:
        user_id = db.execute("SELECT id FROM users WHERE username = ?", (args.username,)).fetchone()[0]
        users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    cookie = module.app.session_interface.get_signing_serializer(module.app).dumps({"user_id": user_id})
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    server = make_server("127.0.0.1", 0, module.app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    result = {"users": users, "username": args.username,
              "browsergym_core": importlib.metadata.version("browsergym-core"),
              "playwright": importlib.metadata.version("playwright")}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            result["chromium"] = browser.version
            context = browser.new_context(viewport={"width": 1280, "height": 720})
            context.add_cookies([{"name": "session", "value": cookie, "url": url}])
            page = context.new_page()
            started = perf_counter()
            # Network idle alone may fire while Chromium is still parsing the
            # old 133k-element page. Wait for parsing and styles before counting.
            page.goto(url + "/messages", wait_until="load", timeout=120000)
            result["load_seconds"] = perf_counter() - started
            result["dom_elements"] = page.locator("*").count()
            result["styles_loaded"] = page.locator("h1").evaluate("el => getComputedStyle(el).fontSize") == "20px"
            print(json.dumps(result), flush=True)
            for name, operation in [("mark_seconds", _pre_extract),
                                    ("dom_snapshot_seconds", extract_dom_snapshot),
                                    ("axtree_seconds", extract_merged_axtree)]:
                started = perf_counter()
                observation = operation(page)
                result[name] = perf_counter() - started
                if name == "axtree_seconds":
                    result["axtree_nodes"] = len(observation["nodes"])
                print(f"{name}: {result[name]:.4f}", flush=True)
            browser.close()
    finally:
        server.shutdown()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
