# Penpot Seed Data

Pre-populated Penpot Docker image with realistic mock data for agent testing.
Data is baked into the Docker image (WebArena style) — no external volumes or seed scripts needed at runtime.

## Quick Start

```bash
# Step 1 (one-time): Generate the DB dump
cd penpot
./scripts/seed-local.sh

# Step 2: Build the image
docker build -t penpot-webarena .

# Step 3: Run
docker run -d --name penpot -p 9001:9001 penpot-webarena

# Reset (wipe all changes, back to clean seed state)
docker rm -f penpot
docker run -d --name penpot -p 9001:9001 penpot-webarena
```

Access Penpot at **http://localhost:9001**

Penpot takes ~30–60 seconds to fully initialize on first `docker run`.

### Credentials

| Role  | Email                     | Password          |
|-------|---------------------------|-------------------|
| Admin | `admin@penpot.local`      | `Admin@Secure123` |
| Users | `alice@designstudio.io`   | `User@Secure123`  |
|       | `bob@designstudio.io`     | `User@Secure123`  |
|       | `carol@designstudio.io`   | `User@Secure123`  |
|       | `david@designstudio.io`   | `User@Secure123`  |
|       | `emma@designstudio.io`    | `User@Secure123`  |
|       | `frank@designstudio.io`   | `User@Secure123`  |
|       | `grace@designstudio.io`   | `User@Secure123`  |
|       | `henry@designstudio.io`   | `User@Secure123`  |

## What's Included

### Users (9 total)

| Full Name      | Email                    | Role                |
|----------------|--------------------------|---------------------|
| Penpot Admin   | admin@penpot.local       | System Admin        |
| Alice Chen     | alice@designstudio.io    | Lead UI/UX Designer |
| Bob Martin     | bob@designstudio.io      | Product Designer    |
| Carol Jones    | carol@designstudio.io    | Brand Designer      |
| David Kim      | david@designstudio.io    | Product Manager     |
| Emma Wilson    | emma@designstudio.io     | Frontend Developer  |
| Frank Oz       | frank@designstudio.io    | Motion Designer     |
| Grace Lee      | grace@designstudio.io    | UX Researcher       |
| Henry Park     | henry@designstudio.io    | Graphic Designer    |

### Teams (2)

#### Design Studio (owner: admin)
Members: Alice, Bob, Carol, Frank, Henry (editors) + David, Emma (viewers) + Grace (editor)

Projects and files:
- **Design System**: Core Components, Typography & Color, Icon Library (shared), Motion Guidelines, Spacing & Grid
- **Brand Identity**: Logo & Marks, Brand Guidelines v2, Social Media Kit, Print Templates
- **Marketing Assets**: Q2 Campaign Banners, Email Newsletter Templates, Conference Booth Design

#### Product Squad (owner: Alice Chen)
Members: Admin, Bob, Carol, David, Emma (editors) + Grace (viewer)

Projects and files:
- **Mobile App v2**: User Research Findings, Wireframes, UI Mockups, Prototype - Onboarding, Handoff Specs
- **Web Dashboard**: Information Architecture, Dashboard Redesign, Accessibility Review, Dark Mode
- **Marketing Site**: Landing Page, Pricing Page, Blog Templates
- **Archive**: Old Landing Page v1, Legacy Dashboard

## How It Works

```
Seed flow (one-time, during development):
  seed-local.sh
    → docker-compose.seed.yml   (temporary Penpot stack)
    → seed_penpot.py            (register users, create teams/projects/files via API)
    → SQL                       (add team memberships)
    → pg_dump → data/penpot_db.sql.gz

Build flow:
  docker build
    → COPY data/penpot_db.sql.gz into image

Runtime flow:
  docker run → start.sh
    → initdb → pg_ctl start → psql < penpot_db.sql.gz → pg_ctl stop
    → supervisord manages: postgresql, redis, penpot-backend, penpot-exporter, nginx
```

## Rebuilding the Seed Data

To change users, teams, projects, or files:

1. Edit [seed_data.json](seed_data.json) with your changes
2. Re-run the seed:
   ```bash
   ./scripts/seed-local.sh
   ```
3. Rebuild the image:
   ```bash
   docker build -t penpot-webarena .
   ```

## Scenarios for Agent Testing

| Scenario | Example Task |
|----------|-------------|
| File navigation | "Open the 'Dashboard Redesign' file in the Web Dashboard project" |
| Project management | "Create a new project called 'Mobile App v3' in Product Squad" |
| File sharing | "Share the 'Icon Library' file with the Product Squad team" |
| Team management | "Invite henry@designstudio.io to the Product Squad team as an editor" |
| File creation | "Create a new file called 'Q3 Banners' in the Marketing Assets project" |
| User lookup | "Who is the Lead UI/UX Designer?" |
| Cross-team work | "List all shared files across all teams" |
| Permission check | "Which users have editor access to the Design Studio team?" |

## File Structure

```
penpot/
├── README.md                     # This file
├── Dockerfile                    # Builds the baked single-container image
├── seed_data.json                # Users, teams, projects, files (source of truth)
├── configs/
│   ├── nginx.conf                # nginx reverse proxy (frontend + backend + exporter)
│   └── supervisord.conf          # Process manager config (pg, redis, penpot-*, nginx)
├── scripts/
│   ├── start.sh                  # Container entrypoint (init DB + launch supervisord)
│   ├── healthcheck.sh            # Docker health probe
│   └── seed-local.sh             # Orchestrates the full seed-and-export flow
├── seed/
│   ├── docker-compose.seed.yml   # Temporary Penpot stack for seeding
│   ├── .env.seed                 # Seed environment variables
│   ├── seed_penpot.py            # Python seeder (register users, create content via API)
│   └── requirements.txt          # Python deps (requests)
└── data/
    └── penpot_db.sql.gz          # Generated by seed-local.sh — baked into image
```

## Pinned Version

This setup uses **Penpot 2.14.1** (latest stable as of April 2026):
- `penpotapp/frontend:2.14.1`
- `penpotapp/backend:2.14.1`
- `penpotapp/exporter:2.14.1`

To upgrade, update the version tag in both `Dockerfile` and `seed/docker-compose.seed.yml`,
then re-run `seed-local.sh` and rebuild.

### Path tool initialization fix

The 2.14.1 frontend emits an initial `nil` mouse position before the pointer
enters the canvas. Selecting **Path (P)** at that point can crash the editor
with `invalid arguments (on pointer constructor)` and `{:x nil, :y nil}`.
Direct agent clicks and keyboard shortcuts commonly trigger this sequence.

The Docker build applies `scripts/patch-path-initialization.cjs` to the pinned
frontend bundle. It filters the unset position in the path position stream
before snapping and preview creation. It does not invent coordinates or alter
saved shapes. The patch is idempotent and rejects unexpected bundle layouts;
revisit it when upgrading Penpot. This is a compiled-bundle backport; upstream
source maps retain the original source, so columns on the edited line may differ.

Run the browser regression against a **disposable** container (it creates test
files in Drafts), using a Python environment with Playwright and Chromium:

```bash
python scripts/smoke-path-drawing.py --url http://localhost:9001
# Also exercise BrowserGym's DOM instrumentation when it is installed:
python scripts/smoke-path-drawing.py --url http://localhost:9001 --browsergym
```

Both toolbar and keyboard activation must work before any canvas pointer event.
Each case draws a line-based heart, waits for autosave, and reloads the file to
verify that the same path geometry persists. Screenshots and JSON results are
written to `/tmp/penpot-path-smoke` (override with `--output`).

### Text tool focus workaround (2.14.1)

After drawing a board, selecting **Text (T)** and clicking once inside the board
can leave focus on the page body. Typing then runs keyboard shortcuts instead of
entering text; issue [#112](https://github.com/webarena-pro/webarena-pro/issues/112)
also reports an Internal Error in the path editor from this sequence. The path
initialization patch above addresses a different failure and does not fix text
focus.

Click a second time at the text position and confirm that the text caret is
visible before typing. Browser automation should wait for a focused
`contenteditable` element. After entering the text, click outside the text box
to commit the edit and wait for autosave before navigating away. This is a
workaround for the pinned upstream frontend, not a backport of a text-tool fix.

The following browser smoke reproduces the missing first-click focus, applies
the second-click workaround when needed, checks a successful save containing
the text, and reloads the file to verify that the text persisted at 1280×720:

```bash
python scripts/smoke-text-entry.py --url http://localhost:9001
```

Use a disposable container: the check creates a file in the seed admin's Drafts.
Results and a screenshot are written to `/tmp/penpot-text-smoke` (override with
`--output`). Revisit the workaround when upgrading Penpot.
