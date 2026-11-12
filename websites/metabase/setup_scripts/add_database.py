#!/usr/bin/env python3
"""
Script to check if my-db is added to Metabase and add it if not.
"""

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

METABASE_URL = os.getenv("METABASE_URL", "http://localhost:3000")
METABASE_USERNAME = os.getenv("METABASE_USERNAME", "admin@admin.com")
METABASE_PASSWORD = os.getenv("METABASE_PASSWORD", "apassword123")

DATABASE_NAME = "my-db"
DATABASE_CONFIG = {
    "name": DATABASE_NAME,
    "engine": "postgres",
    "details": {
        "host": "my-db",  # Docker service name
        "port": 5432,
        "dbname": "sample_data",
        "user": "sample",
        "password": "sample",
        "ssl": False,
    },
}


def get_session_token() -> str | None:
    """Authenticate with Metabase and return session token."""
    try:
        response = httpx.post(
            f"{METABASE_URL}/api/session",
            json={"username": METABASE_USERNAME, "password": METABASE_PASSWORD},
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("id")
    except httpx.HTTPError as e:
        print(f"Failed to authenticate with Metabase: {e}")
        return None


def get_databases(token: str) -> list[dict]:
    """Get list of all databases configured in Metabase."""
    try:
        response = httpx.get(
            f"{METABASE_URL}/api/database",
            headers={"X-Metabase-Session": token},
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("data", [])
    except httpx.HTTPError as e:
        print(f"Failed to get databases: {e}")
        return []


def database_exists(databases: list[dict], name: str) -> bool:
    """Check if a database with the given name exists."""
    return any(db.get("name") == name for db in databases)


def add_database(token: str, config: dict) -> bool:
    """Add a new database to Metabase."""
    try:
        response = httpx.post(
            f"{METABASE_URL}/api/database",
            headers={"X-Metabase-Session": token},
            json=config,
            timeout=30,
        )
        response.raise_for_status()
        db_id = response.json().get("id")
        print(f"Successfully added database '{config['name']}' with ID: {db_id}")
        return True
    except httpx.HTTPStatusError as e:
        print(f"Failed to add database: {e}")
        print(f"Response: {e.response.text}")
        return False
    except httpx.HTTPError as e:
        print(f"Failed to add database: {e}")
        return False


def main():
    print(f"Connecting to Metabase at {METABASE_URL}...")

    token = get_session_token()
    if not token:
        print("Could not authenticate with Metabase. Is it running?")
        sys.exit(1)

    print("Authenticated successfully.")

    databases = get_databases(token)
    print(f"Found {len(databases)} existing database(s):")
    for db in databases:
        print(f"  - {db.get('name')} (id: {db.get('id')}, engine: {db.get('engine')})")

    if database_exists(databases, DATABASE_NAME):
        print(f"\nDatabase '{DATABASE_NAME}' already exists. Nothing to do.")
        return

    print(f"\nDatabase '{DATABASE_NAME}' not found. Adding it now...")
    if add_database(token, DATABASE_CONFIG):
        print("Done!")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
