# Metabase Local Environment

A local Metabase environment with sample e-commerce data, automated setup scripts, and optional browser agent capabilities.

## Overview

This project provides:
- A Docker-based Metabase instance with PostgreSQL backend
- Sample e-commerce database with customers, products, orders, and reviews
- A **setup** service (built from **`Dockerfile`** + **`requirements.txt`**) that runs **`setup_scripts/setup_all.py`** once when you **`docker compose up`**
- The same scripts can be run on the host with **`pip install -r requirements.txt`**

## Prerequisites

- **Docker** with **Compose** (`docker compose` v2 plugin or standalone `docker-compose`)
- **Python 3.11+** only if you run `setup_scripts/` on the host or use the **browser agent** (`metabase-agent`)

## Quick Start

### 1. Clone the repository and open this site

```bash
git clone https://github.com/YOUR-USERNAME/webarena-pro.git
cd webarena-pro/websites/metabase
```

### 2. (Optional) Configure environment variables

For **running setup on your machine** (not in Docker), copy the example env file:

```bash
cp .env.example .env
```

Defaults:

```bash
METABASE_URL=http://localhost:3000
METABASE_USERNAME=admin@admin.com
METABASE_PASSWORD=apassword123
```

The **`setup` service in Compose** does not use `localhost` for Metabase (that would point at the wrong container). `docker-compose.yml` sets `METABASE_URL=http://metabase:3000` for that service. You still open Metabase in the browser at **http://localhost:3000**.

### 3. Start Docker and run automated setup

```bash
docker compose up -d
```

This starts **four** services:

| Service | Role |
|---------|------|
| **metabase** | Metabase on port **3000** |
| **postgres** | Metabase application database |
| **my-db** | Sample e-commerce data (host port **5433**) |
| **setup** | One-shot image: installs deps from **`requirements.txt`**, runs **`setup_scripts/setup_all.py`**, then **exits** |

The **setup** container waits until Metabase and `my-db` are healthy, then configures Metabase (admin user, `my-db` connection, questions, dashboards, `.auth/metabase_admin_state.json`). It is **not** a long-running service; `docker compose ps` will show it as exited after success.

Wait for Metabase on first boot (often 1–2 minutes):

```bash
docker compose ps
docker compose logs -f metabase
```

Metabase is ready when logs show something like `Metabase Initialization COMPLETE`.

Confirm setup finished:

```bash
docker compose logs setup
```

If you need to **re-run** provisioning (e.g. after wiping volumes):

```bash
docker compose run --rm setup
```

**What `setup_all.py` does** (Docker or host):

1. **Create admin user** — complete first-time Metabase setup  
2. **Add database** — connect the sample e-commerce database  
3. **Create SQL query** — “Revenue by Category”  
4. **Create Sales dashboard** — “Sales Overview” with charts  
5. **Create AgentLab documentation** — docs dashboard  
6. **Save auth state** — write `.auth/metabase_admin_state.json` for browser agent tasks  

When the **setup container** runs, log lines may show `METABASE_URL` as `http://metabase:3000`. Open dashboards in your browser at **http://localhost:3000** (same paths and IDs as in the log).

Example output (host run; URL line matches your `METABASE_URL`):

```
==================================================
Metabase Setup
==================================================
URL: http://localhost:3000
Waiting for Metabase at http://localhost:3000...
Metabase is ready.

Step 1/6: Checking first-time setup...
  Creating admin user: admin@admin.com
  First-time setup completed successfully

Authenticated successfully.

Step 2/6: Adding database...
  Created database 'my-db' with ID: 2

Step 3/6: Creating SQL query...
  Created SQL question 'Revenue by Category' with ID: 1

Step 4/6: Creating Sales dashboard...
  Created question 'Orders by Status' with ID: 2
  Created dashboard 'Sales Overview' with ID: 1
  Added header and questions to dashboard

Step 5/6: Creating AgentLab documentation...
  Created dashboard 'AgentLab Documentation' with ID: 2
  Added 5 documentation sections

Step 6/6: Saving auth state for browser agent...
  Auth state saved to ./.auth/metabase_admin_state.json

==================================================
Setup Complete!
==================================================
Sales Dashboard: http://localhost:3000/dashboard/1
AgentLab Docs:   http://localhost:3000/dashboard/2
Auth State:      ./.auth/metabase_admin_state.json
```

### 4. (Alternative) Run setup on the host

If you prefer not to use the setup container, install only what the scripts need:

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python setup_scripts/setup_all.py
```

Or use **`./setup.sh`** if present.

### 5. Python for the browser agent only

The **`metabase_agent`** CLI and its stack are declared in **`pyproject.toml`**. They are **not** installed by the setup Docker image. For agent work, use a venv and editable install:

```bash
pip install -e .
```

### 6. Access Metabase

Open http://localhost:3000 and log in with:
- **Email:** `admin@admin.com`
- **Password:** `apassword123`

## Sample Data

The sample database (`my-db`) contains e-commerce data:

| Table | Description |
|-------|-------------|
| `people` | 30 customers with name, email, location |
| `products` | 30 products with category, vendor, price, rating |
| `orders` | 200 orders with status (pending, paid, shipped, completed, returned) |
| `order_items` | Order line items with quantity, price, discount |
| `reviews` | 80 product reviews with ratings |
| `order_summary` | View joining orders with customer and item data |

## Setup Scripts

Individual scripts are available in `setup_scripts/`:

| Script | Purpose |
|--------|---------|
| `setup_all.py` | All-in-one setup (recommended) |
| `setup_login.py` | First-time Metabase setup only |
| `add_database.py` | Add database connection only |
| `add_sql_query.py` | Create SQL question only |
| `add_dashboard.py` | Create Sales dashboard only |
| `add_documentation.py` | Create AgentLab documentation dashboard |
| `save_auth_state.py` | Save Playwright auth state for browser agent |

Run individual scripts (from the host, after `pip install -r requirements.txt` and with `METABASE_URL=http://localhost:3000` in `.env` if Metabase is exposed on port 3000):

```bash
python setup_scripts/setup_login.py
python setup_scripts/add_database.py
python setup_scripts/add_sql_query.py
python setup_scripts/add_dashboard.py
python setup_scripts/add_documentation.py
python setup_scripts/save_auth_state.py
```

All scripts are **idempotent** — they skip resources that already exist.

## Docker commands

```bash
# Start all services (setup runs once and exits)
docker compose up -d

# One-shot setup only (e.g. after reset)
docker compose run --rm setup

# Stop containers
docker compose down

# Stop and remove volumes (full reset)
docker compose down -v

# Logs
docker compose logs -f metabase
docker compose logs setup

# Restart Metabase
docker compose restart metabase
```

## Troubleshooting

### Metabase not starting
```bash
docker compose ps
docker compose logs metabase
```

### Setup container exits immediately or Metabase looks empty
- Check **`docker compose logs setup`**. Failures often mean Metabase was not reachable at the URL the script uses.
- In Compose, the setup service must use **`METABASE_URL=http://metabase:3000`** (already set in `docker-compose.yml`). Do not change it to `localhost` inside the container.
- Re-run provisioning: **`docker compose run --rm setup`**.

### Setup script fails to authenticate (host or container)
- Ensure Metabase is fully initialized (logs: “Initialization COMPLETE” or similar).
- On the **host**, use **`METABASE_URL=http://localhost:3000`** in `.env`.
- If Metabase was already set up with different credentials, reset with **`docker compose down -v`**.

### Database not syncing
After adding the database, Metabase needs to sync metadata. This happens automatically but can take a minute. You can trigger a manual sync in Metabase UI: Admin > Databases > my-db > Sync database schema.

### Port conflicts
If port 3000 or 5433 is in use, edit `docker-compose.yml` to change the port mappings.

---

## Extra: Browser Agent (Experimental)

This project includes experimental support for a browser agent that can automate Metabase tasks using AI.

### Features

- Autonomous browser operation using Playwright
- AgentLab GenericAgent integration for action decisions
- Multi-provider LLM support via LiteLLM (Gemini, OpenAI, Azure, OpenRouter)
- Vision-enabled agents with screenshot understanding
- Structured task definitions in YAML format
- Comprehensive artifact logging (screenshots, traces, summaries)

### Additional Setup

```bash
# Install Playwright browser
playwright install chromium

# Set your LLM API key
export GEMINI_API_KEY=your-gemini-api-key
# or
export OPENAI_API_KEY=your-openai-api-key
```

### Running the Agent

```bash
# Run a sample task
metabase-agent run --task filter_and_save_question

# Run with a specific model
metabase-agent run --task filter_and_save_question --model gemini/gemini-2.0-flash

# Run in demo mode (visible browser)
metabase-agent run --task filter_and_save_question --demo

# List available tasks
metabase-agent list-tasks
```

### Supported Models

| Provider | Model Examples | API Key Variable |
|----------|---------------|------------------|
| Gemini | `gemini/gemini-2.0-flash`, `gemini/gemini-1.5-pro` | `GEMINI_API_KEY` |
| OpenAI | `gpt-4o`, `gpt-4o-mini` | `OPENAI_API_KEY` |
| Azure | `azure/your-deployment` | `AZURE_OPENAI_API_KEY` |
| OpenRouter | `openrouter/anthropic/claude-3.5-sonnet` | `OPENROUTER_API_KEY` |

### Project structure

Paths are relative to **`websites/metabase/`**:

```
websites/metabase/
├── Dockerfile              # Setup image: pip install -r requirements.txt, run setup_all.py
├── docker-compose.yml      # metabase, postgres, my-db, setup
├── requirements.txt        # Dependencies for setup_scripts/ (httpx, python-dotenv)
├── seed.sql                # Sample data for my-db
├── setup.sh                # Optional shell helper
├── setup_scripts/          # Python setup scripts
│   ├── setup_all.py        # All-in-one setup
│   ├── setup_login.py      # First-time setup
│   ├── add_database.py     # Add database
│   ├── add_sql_query.py    # Create SQL question
│   ├── add_dashboard.py    # Create Sales dashboard
│   ├── add_documentation.py # Create AgentLab docs dashboard
│   └── save_auth_state.py  # Save Playwright auth state
├── .auth/                  # Auth state for browser agent (generated; mounted in setup container)
│   └── metabase_admin_state.json
├── tasks/                  # Browser agent task definitions
│   └── task_*.json
├── src/
│   └── metabase_agent/     # Browser agent (experimental)
│       ├── cli.py          # Command-line interface
│       ├── config.py       # Configuration
│       ├── runner.py       # Task orchestration
│       ├── agent/          # AgentLab adapter
│       ├── env/            # Browser environment
│       ├── tasks/          # Task definitions
│       └── evaluation/     # Success criteria
└── pyproject.toml          # metabase-agent package (pip install -e .)
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "Add feature"`
4. Push to your fork: `git push origin feature/your-feature`
5. Open a Pull Request
