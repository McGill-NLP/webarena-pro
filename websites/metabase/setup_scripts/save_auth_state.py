#!/usr/bin/env python3
"""
Script to generate .auth/metabase_admin_state.json for AgentLab tasks.
Saves a Playwright-compatible storage state with the Metabase session cookie.
Run this after Metabase first-time setup is complete.
"""

import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

METABASE_URL = os.getenv("METABASE_URL", "http://localhost:3000")
METABASE_USERNAME = os.getenv("METABASE_USERNAME", "admin@admin.com")
METABASE_PASSWORD = os.getenv("METABASE_PASSWORD", "apassword123")
AUTH_STATE_PATH = os.getenv("AUTH_STATE_PATH", "./.auth/metabase_admin_state.json")


def get_session_token() -> str | None:
    """Log in to Metabase and return the session token."""
    try:
        response = httpx.post(
            f"{METABASE_URL}/api/session",
            json={"username": METABASE_USERNAME, "password": METABASE_PASSWORD},
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("id")
    except httpx.HTTPError as e:
        print(f"Login failed: {e}")
        return None


def save_auth_state(token: str) -> bool:
    """Save the session token as a Playwright-compatible storage state file."""
    os.makedirs(os.path.dirname(AUTH_STATE_PATH), exist_ok=True)
    state = {
        "cookies": [
            {
                "name": "metabase.SESSION",
                "value": token,
                "domain": "localhost",
                "path": "/",
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            }
        ],
        "origins": [],
    }
    try:
        with open(AUTH_STATE_PATH, "w") as f:
            json.dump(state, f, indent=2)
        return True
    except OSError as e:
        print(f"Failed to write auth state: {e}")
        return False


def main():
    print(f"Logging in to Metabase at {METABASE_URL}...")

    token = get_session_token()
    if not token:
        print("Could not obtain session token. Is Metabase running and setup complete?")
        sys.exit(1)

    print(f"Login successful. Session token: {token[:8]}...")

    if save_auth_state(token):
        print(f"Auth state saved to {AUTH_STATE_PATH}")
        print("\nBrowser agent tasks can now use this auth state for pre-authenticated sessions.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()