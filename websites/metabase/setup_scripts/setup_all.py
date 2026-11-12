#!/usr/bin/env python3
"""
Combined setup script for Metabase.
Runs all setup steps: first-time setup, add database, create SQL query, create dashboard,
AgentLab documentation, and auth state for browser agent tasks.
"""

import json
import os
import sys
import time

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
        "host": os.getenv("MY_DB_HOST", "my-db"),
        "port": 5432,
        "dbname": "sample_data",
        "user": "sample",
        "password": "sample",
        "ssl": False,
    },
}

SQL_QUERY_NAME = "Revenue by Category"
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

SIMPLE_QUESTION_NAME = "Orders by Status"
DASHBOARD_NAME = "Sales Overview"
DOCS_DASHBOARD_NAME = "AgentLab Documentation"
AUTH_STATE_PATH = "./.auth/metabase_admin_state.json"


class MetabaseClient:
    """Simple Metabase API client."""

    def __init__(self, url: str, username: str, password: str):
        self.url = url
        self.token: str | None = None
        self.username = username
        self.password = password

    def is_setup_complete(self) -> bool:
        """Check if Metabase first-time setup is already complete."""
        try:
            response = httpx.get(f"{self.url}/api/session/properties", timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("setup-token") is None and data.get("has-user-setup", False)
        except httpx.HTTPError:
            return False

    def get_setup_token(self) -> str | None:
        """Get the setup token (only available on fresh installs)."""
        try:
            response = httpx.get(f"{self.url}/api/session/properties", timeout=10)
            response.raise_for_status()
            return response.json().get("setup-token")
        except httpx.HTTPError:
            return None

    def complete_first_time_setup(self) -> str | None:
        """Complete the first-time Metabase setup and return session token."""
        setup_token = self.get_setup_token()
        if not setup_token:
            return None

        setup_payload = {
            "token": setup_token,
            "user": {
                "email": self.username,
                "password": self.password,
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
                f"{self.url}/api/setup",
                json=setup_payload,
                timeout=30,
            )
            response.raise_for_status()
            self.token = response.json().get("id")
            return self.token
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                # 403 means setup is already complete, try to authenticate instead
                print("  Setup already complete, authenticating...")
                if self.authenticate():
                    return self.token
            print(f"Failed to complete setup: {e}")
            return None
        except httpx.HTTPError as e:
            print(f"Failed to complete setup: {e}")
            return None

    def authenticate(self) -> bool:
        """Authenticate and store session token."""
        try:
            response = httpx.post(
                f"{self.url}/api/session",
                json={"username": self.username, "password": self.password},
                timeout=10,
            )
            response.raise_for_status()
            self.token = response.json().get("id")
            return True
        except httpx.HTTPError as e:
            print(f"Failed to authenticate: {e}")
            return False

    def _headers(self) -> dict:
        return {"X-Metabase-Session": self.token}

    def get_databases(self) -> list[dict]:
        response = httpx.get(
            f"{self.url}/api/database", headers=self._headers(), timeout=10
        )
        response.raise_for_status()
        return response.json().get("data", [])

    def get_database_id(self, name: str) -> int | None:
        for db in self.get_databases():
            if db.get("name") == name:
                return db.get("id")
        return None

    def add_database(self, config: dict) -> int | None:
        response = httpx.post(
            f"{self.url}/api/database",
            headers=self._headers(),
            json=config,
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("id")

    def get_cards(self) -> list[dict]:
        response = httpx.get(
            f"{self.url}/api/card", headers=self._headers(), timeout=10
        )
        response.raise_for_status()
        return response.json()

    def get_card_id(self, name: str) -> int | None:
        for card in self.get_cards():
            if card.get("name") == name:
                return card.get("id")
        return None

    def create_card(self, config: dict) -> int | None:
        response = httpx.post(
            f"{self.url}/api/card",
            headers=self._headers(),
            json=config,
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("id")

    def get_dashboards(self) -> list[dict]:
        response = httpx.get(
            f"{self.url}/api/dashboard", headers=self._headers(), timeout=10
        )
        response.raise_for_status()
        return response.json()

    def get_dashboard_id(self, name: str) -> int | None:
        for d in self.get_dashboards():
            if d.get("name") == name:
                return d.get("id")
        return None

    def create_dashboard(self, config: dict) -> int | None:
        response = httpx.post(
            f"{self.url}/api/dashboard",
            headers=self._headers(),
            json=config,
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("id")

    def update_dashboard(self, dashboard_id: int, config: dict) -> bool:
        response = httpx.put(
            f"{self.url}/api/dashboard/{dashboard_id}",
            headers=self._headers(),
            json=config,
            timeout=30,
        )
        response.raise_for_status()
        return True

    def get_table_id(self, database_id: int, table_name: str) -> int | None:
        response = httpx.get(
            f"{self.url}/api/database/{database_id}/metadata",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        for table in response.json().get("tables", []):
            if table.get("name") == table_name:
                return table.get("id")
        return None

    def get_field_id(self, table_id: int, field_name: str) -> int | None:
        response = httpx.get(
            f"{self.url}/api/table/{table_id}/query_metadata",
            headers=self._headers(),
            timeout=10,
        )
        response.raise_for_status()
        for field in response.json().get("fields", []):
            if field.get("name") == field_name:
                return field.get("id")
        return None


def step_first_time_setup(client: MetabaseClient) -> bool:
    """Step 1: Complete first-time Metabase setup if needed."""
    print("Step 1/6: Checking first-time setup...")

    # First, try to authenticate - if it works, setup is already complete
    if client.authenticate():
        print("  Metabase is already configured (authenticated successfully)")
        return True

    # Authentication failed, check if we need to do first-time setup
    if client.is_setup_complete():
        print("  Metabase is already configured")
        return True

    setup_token = client.get_setup_token()
    if not setup_token:
        print("  No setup token available (Metabase may already be configured)")
        return True

    print(f"  Creating admin user: {client.username}")
    token = client.complete_first_time_setup()
    if token:
        print("  First-time setup completed successfully")
        return True
    else:
        print("  First-time setup failed")
        return False


def step_add_database(client: MetabaseClient) -> int:
    """Step 2: Add database if not exists."""
    print("Step 2/6: Adding database...")

    db_id = client.get_database_id(DATABASE_NAME)
    if db_id:
        print(f"  Database '{DATABASE_NAME}' already exists (ID: {db_id})")
        return db_id

    db_id = client.add_database(DATABASE_CONFIG)
    print(f"  Created database '{DATABASE_NAME}' with ID: {db_id}")
    return db_id


def step_add_sql_query(client: MetabaseClient, database_id: int) -> int:
    """Step 3: Add SQL query if not exists."""
    print("Step 3/6: Creating SQL query...")

    card_id = client.get_card_id(SQL_QUERY_NAME)
    if card_id:
        print(f"  SQL question '{SQL_QUERY_NAME}' already exists (ID: {card_id})")
        return card_id

    config = {
        "name": SQL_QUERY_NAME,
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
            "native": {"query": SQL_QUERY, "template-tags": {}},
        },
    }

    card_id = client.create_card(config)
    print(f"  Created SQL question '{SQL_QUERY_NAME}' with ID: {card_id}")
    return card_id


def step_add_dashboard(
    client: MetabaseClient, database_id: int, sql_card_id: int
) -> int:
    """Step 4: Add dashboard with questions."""
    print("Step 4/6: Creating Sales dashboard...")

    # Check if dashboard exists
    dashboard_id = client.get_dashboard_id(DASHBOARD_NAME)
    if dashboard_id:
        print(f"  Dashboard '{DASHBOARD_NAME}' already exists (ID: {dashboard_id})")
        return dashboard_id

    # Get or create simple question
    simple_card_id = client.get_card_id(SIMPLE_QUESTION_NAME)
    if simple_card_id:
        print(f"  Question '{SIMPLE_QUESTION_NAME}' already exists (ID: {simple_card_id})")
    else:
        table_id = client.get_table_id(database_id, "orders")
        if not table_id:
            raise RuntimeError("Could not find 'orders' table")

        field_id = client.get_field_id(table_id, "status")
        if not field_id:
            raise RuntimeError("Could not find 'status' field")

        config = {
            "name": SIMPLE_QUESTION_NAME,
            "display": "pie",
            "visualization_settings": {"pie.show_legend": True, "pie.show_total": True},
            "dataset_query": {
                "database": database_id,
                "type": "query",
                "query": {
                    "source-table": table_id,
                    "aggregation": [["count"]],
                    "breakout": [["field", field_id, None]],
                },
            },
        }
        simple_card_id = client.create_card(config)
        print(f"  Created question '{SIMPLE_QUESTION_NAME}' with ID: {simple_card_id}")

    # Create dashboard
    dashboard_id = client.create_dashboard({
        "name": DASHBOARD_NAME,
        "description": "Overview of sales metrics and order status",
    })
    print(f"  Created dashboard '{DASHBOARD_NAME}' with ID: {dashboard_id}")

    # Add cards to dashboard
    dashcards = [
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
        {
            "id": -2,
            "card_id": sql_card_id,
            "row": 1,
            "col": 0,
            "size_x": 12,
            "size_y": 8,
        },
        {
            "id": -3,
            "card_id": simple_card_id,
            "row": 1,
            "col": 12,
            "size_x": 12,
            "size_y": 8,
        },
    ]

    client.update_dashboard(dashboard_id, {"dashcards": dashcards})
    print("  Added header and questions to dashboard")

    return dashboard_id


def step_add_documentation(client: MetabaseClient) -> int:
    """Step 5: Add AgentLab documentation dashboard."""
    print("Step 5/6: Creating AgentLab documentation...")

    # Check if dashboard exists
    dashboard_id = client.get_dashboard_id(DOCS_DASHBOARD_NAME)
    if dashboard_id:
        print(f"  Dashboard '{DOCS_DASHBOARD_NAME}' already exists (ID: {dashboard_id})")
        return dashboard_id

    # Create dashboard
    dashboard_id = client.create_dashboard({
        "name": DOCS_DASHBOARD_NAME,
        "description": "Documentation for AgentLab browser automation framework",
    })
    print(f"  Created dashboard '{DOCS_DASHBOARD_NAME}' with ID: {dashboard_id}")

    # Documentation sections
    doc_sections = [
        {"title": "AgentLab Documentation", "type": "heading", "row": 0, "col": 0, "size_x": 24, "size_y": 1},
        {
            "type": "text", "row": 1, "col": 0, "size_x": 12, "size_y": 6,
            "content": """## What is AgentLab?

**AgentLab** is a framework for building autonomous browser agents.

### Key Features
- **GenericAgent**: Flexible agent class for observations → actions
- **BrowserGym**: OpenAI Gym interface for browsers
- **Multi-LLM**: Works with Gemini, OpenAI, Claude via LiteLLM
- **Vision**: Understands screenshots and visual elements

### Use Cases
- Automated web testing
- Data extraction and entry
- Workflow automation
- Browser-based task completion""",
        },
        {
            "type": "text", "row": 1, "col": 12, "size_x": 12, "size_y": 6,
            "content": """## How It Works

AgentLab follows an **observation-action loop**:

```
1. Environment → Observation
2. Agent receives Observation
3. Agent decides Action
4. Environment executes Action
5. Repeat until done
```

### Observation (what agent sees)
- Screenshot, URL, DOM tree, page metadata

### Action (what agent does)
- click, type, scroll, goto, press key""",
        },
        {
            "type": "text", "row": 7, "col": 0, "size_x": 12, "size_y": 6,
            "content": """## Quick Integration

**1. Install**
```bash
pip install agentlab browsergym playwright
playwright install chromium
```

**2. Set API Key**
```bash
export GEMINI_API_KEY=your-key
```

**3. Create Agent**
```python
from agentlab.agents import GenericAgent
agent = GenericAgent(model="gemini/gemini-2.0-flash")
```

**4. Run Loop**
```python
obs = env.reset(start_url="http://...")
while not done:
    action = agent.get_action(obs)
    obs, reward, done, info = env.step(action)
```""",
        },
        {
            "type": "text", "row": 7, "col": 12, "size_x": 12, "size_y": 6,
            "content": """## Supported LLM Providers

| Provider | Models | Env Variable |
|----------|--------|--------------|
| **Gemini** | gemini-2.0-flash | `GEMINI_API_KEY` |
| **OpenAI** | gpt-4o, gpt-4o-mini | `OPENAI_API_KEY` |
| **Anthropic** | claude-3.5-sonnet | `ANTHROPIC_API_KEY` |
| **OpenRouter** | Any model | `OPENROUTER_API_KEY` |

### Best Practices
- ✅ Use vision-enabled models (Gemini, GPT-4o)
- ✅ Save screenshots for debugging
- ✅ Set max_steps limits
- ✅ Run headed mode when debugging
- ❌ Don't skip artifact logging""",
        },
    ]

    # Build dashcards
    dashcards = []
    for i, section in enumerate(doc_sections):
        if section["type"] == "heading":
            dashcard = {
                "id": -(i + 1),
                "card_id": None,
                "row": section["row"],
                "col": section["col"],
                "size_x": section["size_x"],
                "size_y": section["size_y"],
                "visualization_settings": {
                    "virtual_card": {"name": None, "display": "heading", "visualization_settings": {}, "dataset_query": {}, "archived": False},
                    "text": section["title"],
                },
            }
        else:
            dashcard = {
                "id": -(i + 1),
                "card_id": None,
                "row": section["row"],
                "col": section["col"],
                "size_x": section["size_x"],
                "size_y": section["size_y"],
                "visualization_settings": {
                    "virtual_card": {"name": None, "display": "text", "visualization_settings": {}, "dataset_query": {}, "archived": False},
                    "text": section["content"],
                },
            }
        dashcards.append(dashcard)

    client.update_dashboard(dashboard_id, {"dashcards": dashcards})
    print(f"  Added {len(dashcards)} documentation sections")

    return dashboard_id


def step_save_auth_state(client: MetabaseClient) -> bool:
    """Step 6: Save auth state for browser agent tasks."""
    print("Step 6/6: Saving auth state for browser agent...")

    if not client.token:
        print("  No session token available")
        return False

    os.makedirs(os.path.dirname(AUTH_STATE_PATH), exist_ok=True)
    state = {
        "cookies": [
            {
                "name": "metabase.SESSION",
                "value": client.token,
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
        print(f"  Auth state saved to {AUTH_STATE_PATH}")
        return True
    except OSError as e:
        print(f"  Failed to write auth state: {e}")
        return False


def wait_for_metabase(url: str, timeout: int = 120) -> bool:
    """Wait for Metabase to be ready."""
    print(f"Waiting for Metabase at {url}...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = httpx.get(f"{url}/api/health", timeout=5)
            if response.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(2)
    return False


def main():
    print("=" * 50)
    print("Metabase Setup")
    print("=" * 50)
    print(f"URL: {METABASE_URL}")
    print("")

    # Wait for Metabase to be ready
    if not wait_for_metabase(METABASE_URL):
        print("Metabase did not become ready in time. Is it running?")
        sys.exit(1)
    print("Metabase is ready.\n")

    client = MetabaseClient(METABASE_URL, METABASE_USERNAME, METABASE_PASSWORD)

    try:
        # Step 1: First-time setup (creates admin user if needed)
        if not step_first_time_setup(client):
            sys.exit(1)

        # Ensure we're authenticated (should already be from step 1)
        if not client.token:
            if not client.authenticate():
                print("Could not authenticate with Metabase.")
                sys.exit(1)
            print("Authenticated successfully.")
        print("")

        database_id = step_add_database(client)
        print("")

        sql_card_id = step_add_sql_query(client, database_id)
        print("")

        dashboard_id = step_add_dashboard(client, database_id, sql_card_id)
        print("")

        docs_dashboard_id = step_add_documentation(client)
        print("")

        step_save_auth_state(client)
        print("")

    except httpx.HTTPStatusError as e:
        print(f"API error: {e}")
        print(f"Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    print("=" * 50)
    print("Setup Complete!")
    print("=" * 50)
    print(f"Sales Dashboard: {METABASE_URL}/dashboard/{dashboard_id}")
    print(f"AgentLab Docs:   {METABASE_URL}/dashboard/{docs_dashboard_id}")
    print(f"Auth State:      {AUTH_STATE_PATH}")


if __name__ == "__main__":
    main()
