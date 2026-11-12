#!/usr/bin/env python3
"""
Script to create a SQL native query in Metabase.
Creates a "Revenue by Category" query that analyzes product sales.
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
QUERY_NAME = "Revenue by Category"

SQL_QUERY = """
SELECT 
    p.category,
    COUNT(DISTINCT o.id) AS total_orders,
    SUM(oi.quantity) AS units_sold,
    ROUND(SUM(oi.subtotal)::numeric, 2) AS total_revenue,
    ROUND(AVG(oi.subtotal)::numeric, 2) AS avg_order_value
FROM order_items oi
JOIN products p ON p.id = oi.product_id
JOIN orders o ON o.id = oi.order_id
WHERE o.status IN ('paid', 'shipped', 'completed')
GROUP BY p.category
ORDER BY total_revenue DESC
""".strip()


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


def create_sql_question(token: str, database_id: int) -> int | None:
    """Create a native SQL question and return its ID."""
    question_config = {
        "name": QUERY_NAME,
        "display": "table",
        "visualization_settings": {
            "table.pivot": False,
            "column_settings": {
                '["name","total_revenue"]': {"number_style": "currency", "currency": "USD"},
                '["name","avg_order_value"]': {"number_style": "currency", "currency": "USD"},
            },
        },
        "dataset_query": {
            "database": database_id,
            "type": "native",
            "native": {
                "query": SQL_QUERY,
                "template-tags": {},
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
        print(f"Created SQL question '{QUERY_NAME}' with ID: {card_id}")
        return card_id
    except httpx.HTTPStatusError as e:
        print(f"Failed to create SQL question: {e}")
        print(f"Response: {e.response.text}")
        return None
    except httpx.HTTPError as e:
        print(f"Failed to create SQL question: {e}")
        return None


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

    # Check if question already exists
    cards = get_existing_cards(token)
    for c in cards:
        if c.get("name") == QUERY_NAME:
            print(f"SQL question '{QUERY_NAME}' already exists (ID: {c.get('id')}). Nothing to do.")
            return

    # Create the SQL question
    card_id = create_sql_question(token, database_id)
    if not card_id:
        sys.exit(1)

    print(f"\nDone! Question available at: {METABASE_URL}/question/{card_id}")
    print(f"\nSQL Query:\n{SQL_QUERY}")


if __name__ == "__main__":
    main()
