#!/usr/bin/env python3
"""
Script to create an AgentLab documentation dashboard in Metabase.
Documents AgentLab capabilities, architecture, and integration guide.
"""

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

METABASE_URL = os.getenv("METABASE_URL", "http://localhost:3000")
METABASE_USERNAME = os.getenv("METABASE_USERNAME", "admin@admin.com")
METABASE_PASSWORD = os.getenv("METABASE_PASSWORD", "apassword123")

DASHBOARD_NAME = "AgentLab Documentation"

# Documentation content as text cards
DOC_SECTIONS = [
    {
        "title": "AgentLab Documentation",
        "type": "heading",
        "row": 0,
        "col": 0,
        "size_x": 24,
        "size_y": 1,
    },
    {
        "title": "What is AgentLab?",
        "type": "text",
        "row": 1,
        "col": 0,
        "size_x": 12,
        "size_y": 6,
        "content": """## What is AgentLab?

**AgentLab** is a framework for building autonomous browser agents that can complete tasks in web applications.

### Key Features

- **GenericAgent**: A flexible agent class that takes observations and returns actions
- **BrowserGym Integration**: Works with browser environments using the OpenAI Gym interface
- **Multi-LLM Support**: Compatible with various LLM providers via LiteLLM
- **Vision Capabilities**: Agents can understand screenshots and visual elements
- **Action Space**: Supports clicks, typing, scrolling, navigation, and more

### Use Cases

- Automated web testing
- Data extraction and entry
- Workflow automation
- UI/UX testing with AI
- Browser-based task completion""",
    },
    {
        "title": "How AgentLab Works",
        "type": "text",
        "row": 1,
        "col": 12,
        "size_x": 12,
        "size_y": 6,
        "content": """## How AgentLab Works

AgentLab follows an **observation-action loop**:

### The Agent Loop

```
1. Environment produces Observation
   ↓
2. Agent receives Observation
   ↓
3. Agent decides Action
   ↓
4. Environment executes Action
   ↓
5. Repeat until done
```

### Observation

What the agent "sees":
- Screenshot (image)
- Current URL
- DOM/Accessibility tree
- Page metadata

### Action

What the agent can do:
- `click(element)` - Click an element
- `type(element, text)` - Enter text
- `scroll(direction)` - Scroll the page
- `goto(url)` - Navigate to URL
- `press(key)` - Press keyboard key""",
    },
    {
        "title": "Architecture Overview",
        "type": "text",
        "row": 7,
        "col": 0,
        "size_x": 12,
        "size_y": 7,
        "content": """## Architecture Overview

AgentLab uses a **layered architecture** with clear separation:

### Components

```
┌─────────────────────────────┐
│       Task Runner           │
│  (orchestrates everything)  │
└──────────┬──────────────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐ ┌─────────────┐
│  Agent  │ │ Browser Env │
│ Adapter │ │ (Playwright)│
└────┬────┘ └──────┬──────┘
     │             │
     ▼             ▼
┌─────────┐ ┌─────────────┐
│ AgentLab│ │   Browser   │
│GenericAg│ │   (Chrome)  │
└─────────┘ └─────────────┘
```

### Key Abstractions

- **TaskSpec**: Defines what to accomplish
- **BrowserEnv**: Controls the browser (Gym interface)
- **AgentController**: Wraps AgentLab's GenericAgent
- **Evaluator**: Checks if task succeeded""",
    },
    {
        "title": "Integration Guide",
        "type": "text",
        "row": 7,
        "col": 12,
        "size_x": 12,
        "size_y": 7,
        "content": """## Quick Integration Guide

### Minimal Setup (5 Steps)

**1. Install Dependencies**
```bash
pip install agentlab browsergym playwright
playwright install chromium
```

**2. Set API Key**
```bash
export GEMINI_API_KEY=your-key
# or OPENAI_API_KEY
```

**3. Create Agent Adapter**
```python
from agentlab.agents import GenericAgent

class MyAgent:
    def __init__(self, model="gemini/gemini-2.0-flash"):
        self.agent = GenericAgent(model=model)
    
    def get_action(self, obs):
        return self.agent.get_action(obs)
```

**4. Create Browser Environment**
```python
from browsergym.core.env import BrowserEnv

env = BrowserEnv(headless=True)
obs = env.reset(start_url="http://...")
```

**5. Run the Loop**
```python
while not done:
    action = agent.get_action(obs)
    obs, reward, done, info = env.step(action)
```""",
    },
    {
        "title": "Task Definition Format",
        "type": "text",
        "row": 14,
        "col": 0,
        "size_x": 12,
        "size_y": 6,
        "content": """## Task Definition Format

Tasks are defined in **YAML** for easy editing:

### Example Task

```yaml
id: create_dashboard
name: Create a new dashboard
instruction: |
  Create a new dashboard named "Q1 Sales"
  and add the revenue chart to it.
start_url: http://localhost:3000
max_steps: 20
timeout_seconds: 300
success_criteria:
  - dashboard_exists: "Q1 Sales"
  - has_card_count: 1
tags:
  - dashboard
  - beginner
```

### Fields

| Field | Description |
|-------|-------------|
| `id` | Unique identifier |
| `instruction` | Natural language task |
| `max_steps` | Step limit |
| `success_criteria` | How to verify success |""",
    },
    {
        "title": "Supported LLM Providers",
        "type": "text",
        "row": 14,
        "col": 12,
        "size_x": 12,
        "size_y": 6,
        "content": """## Supported LLM Providers

AgentLab uses **LiteLLM** for multi-provider support:

### Providers & Models

| Provider | Models | Env Variable |
|----------|--------|--------------|
| **Gemini** | gemini-2.0-flash, gemini-1.5-pro | `GEMINI_API_KEY` |
| **OpenAI** | gpt-4o, gpt-4o-mini | `OPENAI_API_KEY` |
| **Azure** | Your deployments | `AZURE_OPENAI_API_KEY` |
| **OpenRouter** | claude-3.5-sonnet, etc | `OPENROUTER_API_KEY` |
| **Anthropic** | claude-3-opus | `ANTHROPIC_API_KEY` |

### Model Selection

```python
# Gemini (recommended for vision)
agent = GenericAgent(model="gemini/gemini-2.0-flash")

# OpenAI
agent = GenericAgent(model="gpt-4o")

# Via OpenRouter
agent = GenericAgent(model="openrouter/anthropic/claude-3.5-sonnet")
```

Vision-enabled models work best for browser automation.""",
    },
    {
        "title": "Best Practices",
        "type": "text",
        "row": 20,
        "col": 0,
        "size_x": 24,
        "size_y": 5,
        "content": """## Best Practices

### Do's
- ✅ Keep the agent adapter thin and isolated from business logic
- ✅ Save screenshots and action traces for debugging
- ✅ Use headless mode in CI/CD, headed mode for debugging
- ✅ Set reasonable `max_steps` limits to prevent infinite loops
- ✅ Write clear, specific task instructions
- ✅ Use vision-enabled models (Gemini, GPT-4o) for complex UIs

### Don'ts
- ❌ Don't let the agent run without step limits
- ❌ Don't skip artifact logging (you'll regret it when debugging)
- ❌ Don't hardcode element selectors - let the agent find them
- ❌ Don't use text-only models for visual tasks

### Debugging Tips
1. Run in `--demo` mode to see the browser
2. Check screenshots in the artifacts folder
3. Review the action trace JSON
4. Lower `max_steps` when testing new tasks""",
    },
]


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


def create_dashboard(token: str) -> int | None:
    """Create the documentation dashboard."""
    dashboard_config = {
        "name": DASHBOARD_NAME,
        "description": "Documentation for AgentLab browser automation framework",
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


def build_dashcards() -> list[dict]:
    """Build dashcard configurations from documentation sections."""
    dashcards = []

    for i, section in enumerate(DOC_SECTIONS):
        if section["type"] == "heading":
            dashcard = {
                "id": -(i + 1),
                "card_id": None,
                "row": section["row"],
                "col": section["col"],
                "size_x": section["size_x"],
                "size_y": section["size_y"],
                "visualization_settings": {
                    "virtual_card": {
                        "name": None,
                        "display": "heading",
                        "visualization_settings": {},
                        "dataset_query": {},
                        "archived": False,
                    },
                    "text": section["title"],
                },
            }
        else:  # text card
            dashcard = {
                "id": -(i + 1),
                "card_id": None,
                "row": section["row"],
                "col": section["col"],
                "size_x": section["size_x"],
                "size_y": section["size_y"],
                "visualization_settings": {
                    "virtual_card": {
                        "name": None,
                        "display": "text",
                        "visualization_settings": {},
                        "dataset_query": {},
                        "archived": False,
                    },
                    "text": section["content"],
                },
            }

        dashcards.append(dashcard)

    return dashcards


def update_dashboard_with_cards(token: str, dashboard_id: int) -> bool:
    """Update dashboard with documentation text cards."""
    dashcards = build_dashcards()

    try:
        response = httpx.put(
            f"{METABASE_URL}/api/dashboard/{dashboard_id}",
            headers={"X-Metabase-Session": token},
            json={"dashcards": dashcards},
            timeout=30,
        )
        response.raise_for_status()
        print(f"Added {len(dashcards)} documentation sections to dashboard")
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

    # Check if dashboard already exists
    dashboards = get_existing_dashboards(token)
    for d in dashboards:
        if d.get("name") == DASHBOARD_NAME:
            print(f"Dashboard '{DASHBOARD_NAME}' already exists (ID: {d.get('id')}). Nothing to do.")
            return

    # Create the dashboard
    dashboard_id = create_dashboard(token)
    if not dashboard_id:
        sys.exit(1)

    # Add documentation cards
    if not update_dashboard_with_cards(token, dashboard_id):
        sys.exit(1)

    print(f"\nDone! Documentation available at: {METABASE_URL}/dashboard/{dashboard_id}")


if __name__ == "__main__":
    main()
