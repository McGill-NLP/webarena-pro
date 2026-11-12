#!/usr/bin/env python3
"""
Script to create a dashboard with questions in Metabase.
Expects add_sql_query.py to be run first (creates "Revenue by Category").
Creates an additional "Orders by Status" question and a "Sales Overview" dashboard.
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
DASHBOARD_NAME = "Sales Overview"
SQL_QUERY_NAME = "Revenue by Category"  # Created by add_sql_query.py
SIMPLE_QUESTION_NAME = "Orders by Status"


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


def get_database_id(token: str, name: str) -> int | None:
    """Get database ID by name."""
    try:
        response = httpx.get(
            f"{METABASE_URL}/api/database",
            headers={"X-Metabase-Session": token},
            timeout=10,
        )
        response.raise_for_status()
        for db in response.json().get("data", []):
            if db.get("name") == name:
                return db.get("id")
        return None
    except httpx.HTTPError as e:
        print(f"Failed to get databases: {e}")
        return None


def get_table_id(token: str, database_id: int, table_name: str) -> int | None:
    """Get table ID by name within a database."""
    try:
        response = httpx.get(
            f"{METABASE_URL}/api/database/{database_id}/metadata",
            headers={"X-Metabase-Session": token},
            timeout=30,
        )
        response.raise_for_status()
        for table in response.json().get("tables", []):
            if table.get("name") == table_name:
                return table.get("id")
        return None
    except httpx.HTTPError as e:
        print(f"Failed to get table metadata: {e}")
        return None


def get_field_id(token: str, table_id: int, field_name: str) -> int | None:
    """Get field ID by name within a table."""
    try:
        response = httpx.get(
            f"{METABASE_URL}/api/table/{table_id}/query_metadata",
            headers={"X-Metabase-Session": token},
            timeout=10,
        )
        response.raise_for_status()
        for field in response.json().get("fields", []):
            if field.get("name") == field_name:
                return field.get("id")
        return None
    except httpx.HTTPError as e:
        print(f"Failed to get field metadata: {e}")
        return None


def get_existing_cards(token: str) -> list[dict]:
    """Get all existing cards/questions."""
    try:
        response = httpx.get(
            f"{METABASE_URL}/api/card",
            headers={"X-Metabase-Session": token},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        print(f"Failed to get cards: {e}")
        return []


def get_existing_dashboards(token: str) -> list[dict]:
    """Get all existing dashboards."""
    try:
        response = httpx.get(
            f"{METABASE_URL}/api/dashboard",
            headers={"X-Metabase-Session": token},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        print(f"Failed to get dashboards: {e}")
        return []


def get_card_id_by_name(cards: list[dict], name: str) -> int | None:
    """Find a card ID by name."""
    for c in cards:
        if c.get("name") == name:
            return c.get("id")
    return None


def create_simple_question(
    token: str, database_id: int, table_id: int, status_field_id: int
) -> int | None:
    """Create an 'Orders by Status' question and return its ID."""
    question_config = {
        "name": SIMPLE_QUESTION_NAME,
        "display": "pie",
        "visualization_settings": {
            "pie.show_legend": True,
            "pie.show_total": True,
        },
        "dataset_query": {
            "database": database_id,
            "type": "query",
            "query": {
                "source-table": table_id,
                "aggregation": [["count"]],
                "breakout": [["field", status_field_id, None]],
            },
        },
    }

    try:
        response = httpx.post(
            f"{METABASE_URL}/api/card",
            headers={"X-Metabase-Session": token},
            json=question_config,
            timeout=30,
        )
        response.raise_for_status()
        card_id = response.json().get("id")
        print(f"Created question '{SIMPLE_QUESTION_NAME}' with ID: {card_id}")
        return card_id
    except httpx.HTTPStatusError as e:
        print(f"Failed to create question: {e}")
        print(f"Response: {e.response.text}")
        return None
    except httpx.HTTPError as e:
        print(f"Failed to create question: {e}")
        return None


def create_dashboard(token: str) -> int | None:
    """Create a dashboard and return its ID."""
    dashboard_config = {
        "name": DASHBOARD_NAME,
        "description": "Overview of sales metrics and order status",
    }

    try:
        response = httpx.post(
            f"{METABASE_URL}/api/dashboard",
            headers={"X-Metabase-Session": token},
            json=dashboard_config,
            timeout=30,
        )
        response.raise_for_status()
        dashboard_id = response.json().get("id")
        print(f"Created dashboard '{DASHBOARD_NAME}' with ID: {dashboard_id}")
        return dashboard_id
    except httpx.HTTPStatusError as e:
        print(f"Failed to create dashboard: {e}")
        print(f"Response: {e.response.text}")
        return None
    except httpx.HTTPError as e:
        print(f"Failed to create dashboard: {e}")
        return None


def update_dashboard_with_cards(
    token: str, dashboard_id: int, sql_card_id: int, simple_card_id: int
) -> bool:
    """Update dashboard with header and question cards."""
    dashcards = [
        # Header text card (spans full width at top)
        {
            "id": -1,
            "card_id": None,
            "row": 0,
            "col": 0,
            "size_x": 24,
            "size_y": 1,
            "visualization_settings": {
                "virtual_card": {
                    "name": None,
                    "display": "heading",
                    "visualization_settings": {},
                    "dataset_query": {},
                    "archived": False,
                },
                "text": "Sales Overview Dashboard",
            },
        },
        # SQL Query card (Revenue by Category) - left side
        {
            "id": -2,
            "card_id": sql_card_id,
            "row": 1,
            "col": 0,
            "size_x": 12,
            "size_y": 8,
        },
        # Simple question card (Orders by Status) - right side
        {
            "id": -3,
            "card_id": simple_card_id,
            "row": 1,
            "col": 12,
            "size_x": 12,
            "size_y": 8,
        },
    ]

    try:
        response = httpx.put(
            f"{METABASE_URL}/api/dashboard/{dashboard_id}",
            headers={"X-Metabase-Session": token},
            json={"dashcards": dashcards},
            timeout=30,
        )
        response.raise_for_status()
        print("Added header and questions to dashboard successfully")
        return True
    except httpx.HTTPStatusError as e:
        print(f"Failed to update dashboard: {e}")
        print(f"Response: {e.response.text}")
        return False
    except httpx.HTTPError as e:
        print(f"Failed to update dashboard: {e}")
        return False


def main():
    print(f"Connecting to Metabase at {METABASE_URL}...")

    token = get_session_token()
    if not token:
        print("Could not authenticate with Metabase. Is it running?")
        sys.exit(1)
    print("Authenticated successfully.")

    # Check if database exists
    database_id = get_database_id(token, DATABASE_NAME)
    if not database_id:
        print(f"Database '{DATABASE_NAME}' not found. Run add_database.py first.")
        sys.exit(1)
    print(f"Found database '{DATABASE_NAME}' with ID: {database_id}")

    # Check if dashboard already exists
    dashboards = get_existing_dashboards(token)
    for d in dashboards:
        if d.get("name") == DASHBOARD_NAME:
            print(f"Dashboard '{DASHBOARD_NAME}' already exists (ID: {d.get('id')}). Nothing to do.")
            return

    # Get existing cards
    cards = get_existing_cards(token)

    # Check for SQL query (must exist - created by add_sql_query.py)
    sql_card_id = get_card_id_by_name(cards, SQL_QUERY_NAME)
    if not sql_card_id:
        print(f"SQL question '{SQL_QUERY_NAME}' not found. Run add_sql_query.py first.")
        sys.exit(1)
    print(f"Found SQL question '{SQL_QUERY_NAME}' with ID: {sql_card_id}")

    # Check if simple question already exists, or create it
    simple_card_id = get_card_id_by_name(cards, SIMPLE_QUESTION_NAME)
    if simple_card_id:
        print(f"Question '{SIMPLE_QUESTION_NAME}' already exists (ID: {simple_card_id}).")
    else:
        # Get table and field IDs for the simple query
        table_id = get_table_id(token, database_id, "orders")
        if not table_id:
            print("Could not find 'orders' table. Is the database synced?")
            sys.exit(1)
        print(f"Found 'orders' table with ID: {table_id}")

        status_field_id = get_field_id(token, table_id, "status")
        if not status_field_id:
            print("Could not find 'status' field in orders table.")
            sys.exit(1)
        print(f"Found 'status' field with ID: {status_field_id}")

        # Create the simple question
        simple_card_id = create_simple_question(token, database_id, table_id, status_field_id)
        if not simple_card_id:
            sys.exit(1)

    # Create the dashboard
    dashboard_id = create_dashboard(token)
    if not dashboard_id:
        sys.exit(1)

    # Update dashboard with header and both questions
    if not update_dashboard_with_cards(token, dashboard_id, sql_card_id, simple_card_id):
        sys.exit(1)

    print(f"\nDone! Dashboard available at: {METABASE_URL}/dashboard/{dashboard_id}")


if __name__ == "__main__":
    main()
