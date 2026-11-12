#!/usr/bin/env python3
"""Verify the exact protected Mattermost posts through the public API."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8065")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="Admin@Secure123")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "protected_task_messages.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api = args.url.rstrip("/") + "/api/v4"
    session = requests.Session()
    login = session.post(
        f"{api}/users/login",
        json={"login_id": args.username, "password": args.password},
        timeout=30,
    )
    login.raise_for_status()
    token = login.headers["Token"]
    headers = {"Authorization": f"Bearer {token}"}

    manifest = json.loads(args.manifest.read_text())
    verified = 0
    for expected in manifest:
        if not expected["original_synthetic"]:
            continue
        response = session.get(
            f"{api}/posts/{expected['post_id']}", headers=headers, timeout=30
        )
        response.raise_for_status()
        actual = response.json()
        actual_hash = hashlib.sha256(actual["message"].encode()).hexdigest()
        checks = {
            "message": actual["message"] == expected["exact_message"],
            "sha256": actual_hash == expected["sha256"],
            "create_at": actual["create_at"] == expected["create_at_ms"],
            "not_deleted": actual["delete_at"] == 0,
        }
        failed = [name for name, value in checks.items() if not value]
        if failed:
            raise RuntimeError(
                f"{expected['evidence_id']} ({expected['post_id']}) failed: "
                + ", ".join(failed)
            )
        verified += 1

    print(
        f"Verified {verified} original protected posts: exact text, SHA-256, "
        "timestamp, and deletion state all match."
    )
    print(
        "Rank/newest-100, E19, membership, and unread assertions are enforced "
        "by finalize_task_ready_seed.sql."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
