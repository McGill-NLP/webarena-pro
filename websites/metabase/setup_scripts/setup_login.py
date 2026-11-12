#!/usr/bin/env python3
"""
Script to complete Metabase first-time setup.
Creates the admin account on a fresh Metabase installation.
"""

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

METABASE_URL = os.getenv("METABASE_URL", "http://localhost:3000")
METABASE_USERNAME = os.getenv("METABASE_USERNAME", "admin@admin.com")
METABASE_PASSWORD = os.getenv("METABASE_PASSWORD", "apassword123")


def get_setup_token() -> str | None:
    """Get the setup token from Metabase (only available on fresh installs)."""
    try:
        response = httpx.get(f"{METABASE_URL}/api/session/properties", timeout=10)
        response.raise_for_status()
        return response.json().get("setup-token")
    except httpx.HTTPError as e:
        print(f"Failed to get session properties: {e}")
        return None


def is_setup_complete() -> bool:
    """Check if Metabase setup is already complete."""
    try:
        response = httpx.get(f"{METABASE_URL}/api/session/properties", timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("setup-token") is None and data.get("has-user-setup", False)
    except httpx.HTTPError:
        return False


def complete_setup(setup_token: str) -> str | None:
    """Complete the first-time Metabase setup and return session token."""
    setup_payload = {
        "token": setup_token,
        "user": {
            "email": METABASE_USERNAME,
            "password": METABASE_PASSWORD,
            "first_name": "Admin",
            "last_name": "User",
            "site_name": "Metabase Agent",
        },
        "prefs": {
            "site_name": "Metabase Agent",
            "allow_tracking": False,
        },
    }

    try:
        response = httpx.post(
            f"{METABASE_URL}/api/setup",
            json=setup_payload,
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("id")
    except httpx.HTTPStatusError as e:
        print(f"Failed to complete setup: {e}")
        print(f"Response: {e.response.text}")
        return None
    except httpx.HTTPError as e:
        print(f"Failed to complete setup: {e}")
        return None


def main():
    print(f"Connecting to Metabase at {METABASE_URL}...")

    # Check if setup is already complete
    if is_setup_complete():
        print("Metabase setup is already complete. Nothing to do.")
        return

    # Get setup token
    setup_token = get_setup_token()
    if not setup_token:
        print("No setup token available. Metabase may already be configured.")
        return

    print("Found setup token. Completing first-time setup...")
    print(f"  Creating admin user: {METABASE_USERNAME}")

    session_token = complete_setup(setup_token)
    if session_token:
        print("Setup completed successfully!")
        print(f"  Session token: {session_token[:8]}...")
    else:
        print("Setup failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
