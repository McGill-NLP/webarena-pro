#!/usr/bin/env python3
"""Materialize the x-lite seed JSON into SQLite during Docker build."""

import os
import sys


APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import app as x_lite_app  # noqa: E402


def main():
    db_path = x_lite_app.DB_PATH
    if os.path.exists(db_path):
        os.remove(db_path)

    with x_lite_app.app.app_context():
        x_lite_app.init_db()

    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print(f"Wrote {db_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
