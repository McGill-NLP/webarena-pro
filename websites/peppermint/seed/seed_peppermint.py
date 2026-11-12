#!/usr/bin/env python3
"""
Peppermint seeder — populates a running Peppermint instance via the REST API.

Usage:
    python seed_peppermint.py

Environment (read from ../.env.seed or shell):
    PEPPERMINT_URL   Base URL of the Peppermint API server (default: http://localhost:5003)
    ADMIN_EMAIL      Admin email (default: admin@admin.com)
    ADMIN_PASSWORD   Admin password (default: 1234)
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
ENV_FILE = Path(__file__).parent / ".env.seed"
DATA_FILE = ROOT / "seed_data.json"

# Load .env.seed if present
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

BASE_URL = os.environ.get("PEPPERMINT_URL", "http://localhost:5003").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@admin.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")

# ── Helpers ───────────────────────────────────────────────────────────────────

session = requests.Session()
session.headers["Content-Type"] = "application/json"


def api(method: str, path: str, token: str | None = None, **kwargs):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = session.request(method, f"{BASE_URL}{path}", headers=headers, timeout=30, **kwargs)
    return r


def login(email: str, password: str) -> str | None:
    r = api("POST", "/api/v1/auth/login", json={"email": email, "password": password})
    if r.ok:
        data = r.json()
        return data.get("token")
    print(f"  LOGIN FAILED {r.status_code}: {r.text[:200]}")
    return None


def wait_for_api(max_wait: int = 120):
    print(f"Waiting for API at {BASE_URL} ...")
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/", timeout=5)
            if r.status_code < 500:
                print("  API is up.")
                return True
        except Exception:
            pass
        time.sleep(3)
    print(f"  ERROR: API not ready after {max_wait}s")
    return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    data = json.loads(DATA_FILE.read_text())

    if not wait_for_api():
        sys.exit(1)

    # Give the API a moment to finish Prisma migrations
    time.sleep(5)

    # ── Login as admin ────────────────────────────────────────────────────────
    print(f"\nLogging in as {ADMIN_EMAIL}...")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not admin_token:
        # Retry once after a delay — migrations may still be running
        time.sleep(10)
        admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not admin_token:
        print("Failed to login as admin. Exiting.")
        sys.exit(1)
    print("  OK")

    # ── Get admin profile ─────────────────────────────────────────────────────
    r = api("GET", "/api/v1/auth/profile", admin_token)
    admin_id = r.json().get("id") if r.ok else None

    # ── Create users ──────────────────────────────────────────────────────────
    user_tokens: dict[str, str] = {ADMIN_EMAIL: admin_token}
    user_ids: dict[str, str] = {ADMIN_EMAIL: admin_id}
    user_names: dict[str, str] = {ADMIN_EMAIL: "Admin"}

    print(f"\nCreating {len(data['users'])} users...")
    for u in data["users"]:
        r = api(
            "POST", "/api/v1/auth/user/register", admin_token,
            json={"name": u["name"], "email": u["email"],
                  "password": u["password"], "admin": u.get("admin", False)},
        )
        if r.ok:
            body = r.json()
            uid = body.get("id") or body.get("user", {}).get("id")
            user_ids[u["email"]] = uid
            user_names[u["email"]] = u["name"]
            print(f"  Created: {u['email']} (id={uid})")
        else:
            print(f"  Skipped (may exist): {u['email']} — {r.status_code} {r.text[:80]}")
            # Try to log in so we can post comments as them later
            tok = login(u["email"], u["password"])
            if tok:
                user_tokens[u["email"]] = tok
            # Fetch their ID via users list
            continue

        # Log in as the newly created user to get their token
        tok = login(u["email"], u["password"])
        if tok:
            user_tokens[u["email"]] = tok

    # Fetch full user list to backfill any missing IDs
    r = api("GET", "/api/v1/users/all", admin_token)
    if r.ok:
        for pu in r.json():
            email = pu.get("email")
            if email and email not in user_ids:
                user_ids[email] = pu.get("id")
                user_names[email] = pu.get("name", email)
            elif email and not user_ids.get(email):
                user_ids[email] = pu.get("id")

    # ── Create tickets ────────────────────────────────────────────────────────
    print(f"\nCreating {len(data['tickets'])} tickets...")
    for t in data["tickets"]:
        # Build engineer (assignee) field
        engineer = None
        assigned_email = t.get("assignedTo")
        if assigned_email and user_ids.get(assigned_email):
            engineer = {
                "id": user_ids[assigned_email],
                "name": user_names.get(assigned_email, assigned_email),
            }

        body: dict = {
            "name": t["title"],
            "detail": t["detail"],
            "priority": t.get("priority", "low"),
            "type": t.get("type", "support"),
        }
        if engineer:
            body["engineer"] = engineer

        r = api("POST", "/api/v1/ticket/create", admin_token, json=body)
        if not r.ok:
            print(f"  FAILED to create '{t['title'][:45]}': {r.status_code} {r.text[:100]}")
            continue

        ticket_id = r.json().get("id")
        print(f"  Ticket: '{t['title'][:45]}' (id={ticket_id})")

        # Update status if not the default
        status = t.get("status", "needs_support")
        if status and status != "needs_support":
            sr = api("PUT", "/api/v1/ticket/update", admin_token,
                     json={"id": ticket_id, "status": status})
            if not sr.ok:
                # Fallback: try the dedicated status endpoint
                api("PUT", "/api/v1/ticket/status/update", admin_token,
                    json={"id": ticket_id, "status": status})

        # Add comments
        for c in t.get("comments", []):
            commenter_email = c.get("userEmail", ADMIN_EMAIL)
            tok = user_tokens.get(commenter_email, admin_token)
            cr = api("POST", "/api/v1/ticket/comment", tok,
                     json={"id": ticket_id, "text": c["text"],
                           "public": c.get("public", False)})
            if not cr.ok:
                print(f"    Comment failed: {cr.status_code} {cr.text[:80]}")

    print("\nSeeding complete!")


if __name__ == "__main__":
    main()
