# Peppermint Seed Data

Pre-populated Peppermint helpdesk Docker image with realistic mock data for agent testing.
Data is baked into the Docker image (WebArena style) — no external volumes or seed scripts needed at runtime.

## Quick Start

```bash
# Build the image (seeding happens automatically during build — no pre-steps needed)
docker build -t peppermint-webarena .

# Run
docker run -d --name peppermint -p 3000:3000 -p 5003:5003 peppermint-webarena

# Reset (wipe all changes, back to clean seed state)
docker rm -f peppermint
docker run -d --name peppermint -p 3000:3000 -p 5003:5003 peppermint-webarena
```

Access Peppermint at **http://localhost:3000**

The health probe requires both a responding frontend (HTTP 2xx/3xx on port
3000 at Next.js's `HOSTNAME` bind address) and the login API (HTTP 200 or 401
from `/api/v1/auth/check` on loopback port 5003). These probes bypass HTTP proxies.
A frontend-only cold start remains unhealthy until the API is listening. Each
probe bounds both requests and reports which component is not ready without
printing response bodies or credentials. The Harbor exporter packages the same
probe to support existing immutable site images; keep both copies in sync.

After creating a ticket at `/new`, the app returns to the existing `/issues`
list. The image repairs the upstream post-create link to the missing `/tickets`
route in both client and server bundles.

Note: `docker build` takes several minutes — it boots Peppermint internally to seed the database and bake it into the image.

### Credentials

| Role  | Email                        | Password      |
|-------|------------------------------|---------------|
| Admin | `admin@admin.com`            | `1234`        |
| Agent | `james@peppermint.local`     | `Password1!`  |
| Agent | `priya@peppermint.local`     | `Password1!`  |
| Agent | `marcus@peppermint.local`    | `Password1!`  |

## What's Included

### Users (100 total)

| Full Name     | Email                     | Role  |
|---------------|---------------------------|-------|
| Admin         | admin@admin.com           | Admin |
| James Carter  | james@peppermint.local    | Agent |
| Priya Sharma  | priya@peppermint.local    | Agent |
| Marcus Lee    | marcus@peppermint.local   | Agent |

The four users above are the original interactive accounts. The additive GLPI
corpus contributes 96 non-admin personas with deterministic pseudonymous names
and `@peppermint.local` email addresses. They represent 615 source contributors:

- 500 appear as ticket creators
- 23 appear as ticket assignees
- 420 appear as commenters

The consolidation only groups contributors with the same exact role
combination. The 96-persona directory contains 77 creator personas, 5 assignee
personas, and 65 commenter personas; personas can have more than one role. The
complete many-to-one source-login mapping remains auditable in
`data/glpi_user_mapping.json`, and every imported persona uses the local seed
password `Password1!`.

The Internal Users view shows all 100 accounts by default and includes 100 in
its page-size selector. The image also repairs an upstream `length` typo that
otherwise hides the table's pagination controls.

### Tickets (1,000 total; 2,000 comments)

The image combines two independent seed layers:

- 118 original Peppermint tickets and their 81 comments from `seed_data.json`
- 882 additive tickets and 1,919 comments adapted from public
  [GLPI issues](https://github.com/glpi-project/glpi/issues)

The original users, tickets, and comments are loaded first and are not rewritten
by the expansion. Imported records use native helpdesk titles and sections;
GitHub product prefixes, contribution checklists, empty template answers, and
raw Markdown headings are removed. Source links and contributor/date provenance
are retained in the structured expansion metadata, not in visible ticket or
comment text. Imported descriptions are seeded as native rich-text blocks so
line breaks render correctly. Ticket creators, upstream assignees, and comment
authors map through the role-matched pseudonymous personas;
genuinely unassigned source issues remain unassigned. Open GLPI issues map to
`in_progress` or `needs_support`; resolved issues map to `done` and are closed
so the UI's open/closed filter behaves realistically.

### Clients (9 total)

Peppermint's original `internal` client is preserved. The additive corpus adds
eight fictional organizations with unique local contact details:

- Northstar Health Systems
- Harborview Logistics
- Meridian Education Group
- Pinecrest Financial Services
- Apex Manufacturing
- Bluebird Hospitality
- CivicBridge Public Services
- Lumen Retail Group

Of the 882 imported tickets, 653 are deterministically distributed across all
eight clients (68–97 tickets each) and 229 remain without a client. The 118
original Peppermint tickets are not changed. Client assignments are stable when
the expansion is regenerated and appear in Peppermint's client and ticket views.

The All, Open, and Closed ticket views render 50 tickets per page. Their list
endpoints omit description and other detail-only fields, while individual
ticket requests still return the complete record. List refreshes run every 30
seconds instead of every 5 seconds to avoid repeatedly transferring and
rendering the full 1,000-ticket corpus.

### Knowledge Documents (200 total)

The seed bundle includes two additive document layers:

- 100 original troubleshooting documents in `data/knowledge_base_documents.json`
- 100 adapted GLPI user-guide documents in `data/glpi_knowledge_documents.json`

The GLPI documents are sourced from
[`glpi-project/doc`](https://github.com/glpi-project/doc), retain source-revision
links in their metadata and rendered notes, and are attributed under CC BY-SA
3.0 FR. The original document file remains unchanged.

## How It Works

```
Build flow (docker build):
  Stage 1 (peppermint-src): pull official peppermint image
  Stage 2 (seeder):
    → initdb, start Postgres
    → start Peppermint API (Prisma runs migrations)
    → seed_peppermint.js creates clients, users, tickets, comments via REST API
    → pg_dump | gzip → /seed.sql.gz
  Stage 3 (runtime):
    → initdb, restore /seed.sql.gz (PostgreSQL data baked in)
    → supervisord manages: postgresql, peppermint-api (Fastify), peppermint-client (Next.js)

Runtime flow (docker run):
  start.sh → supervisord (postgres + Fastify API + Next.js client)
```

## Rebuilding the Seed Data

To regenerate only the additive GLPI expansion:

```bash
# A token is recommended because the public issue/comment corpus spans more
# requests than GitHub's unauthenticated hourly allowance. The cache is
# resumable if a rate window is exhausted.
GITHUB_TOKEN=... python3 scripts/build_glpi_seed_assets.py \
  --cache-dir /tmp/peppermint-glpi-api-cache
```

The generator reads the original seed files only to calculate the remaining
counts needed to reach 1,000 tickets, 2,000 comments, and 200 documents. It
writes only `data/glpi_tickets.json` and
`data/glpi_knowledge_documents.json`, plus the auditable
`data/glpi_user_mapping.json` identity map.

To add or repair only the deterministic client assignments in an already-built
expansion without downloading from GitHub or changing corpus membership, run:

```bash
python3 scripts/build_glpi_seed_assets.py --assign-existing-clients
```

To consolidate an existing one-account-per-contributor asset into the 96
role-matched personas without downloading or changing corpus membership, run:

```bash
python3 scripts/build_glpi_seed_assets.py --consolidate-existing-users
```

To change the original seed instead:

1. Edit [seed_data.json](seed_data.json) with your changes
2. Edit [data/knowledge_base_documents.json](data/knowledge_base_documents.json) to add or modify troubleshooting docs
3. Rebuild the image (seeding re-runs automatically):
   ```bash
   docker build -t peppermint-webarena .
   ```

## Ports

| Port | Service                        |
|------|--------------------------------|
| 3000 | Next.js frontend (web UI)      |
| 5003 | Fastify REST API               |

The Next.js frontend proxies all `/api/v1/*` requests to the Fastify server at port 5003.

## Scenarios for Agent Testing

| Scenario | Example Task |
|----------|--------------|
| Ticket triage | "Show all open high-priority tickets" |
| Ticket assignment | "Assign the VPN ticket to Priya" |
| Status update | "Mark the SSL certificate ticket as in progress" |
| Comment | "Add an internal note to the database timeout ticket" |
| User lookup | "Which agent has the most open tickets?" |
| Ticket creation | "Create a new ticket for a broken keyboard, medium priority" |
| Filtering | "List all tickets assigned to Marcus" |
| Closed tickets | "Show all resolved tickets from this week" |

## File Structure

```
peppermint/
├── README.md                     # This file
├── Dockerfile                    # Three-stage build: source → seeder → runtime
├── seed_data.json                # Users and original tickets (source of truth)
├── data/
│   ├── knowledge_base_documents.json  # 100 original troubleshooting documents
│   ├── glpi_tickets.json               # 882 GLPI tickets + 1,919 comments
│   ├── glpi_knowledge_documents.json   # 100 attributed GLPI guide documents
│   └── glpi_user_mapping.json          # Source login → pseudonymous user map
├── configs/
│   └── supervisord.conf          # Manages PostgreSQL, Fastify API, Next.js client
├── scripts/
│   ├── build-seed.sh             # Seeder stage script (runs inside docker build)
│   ├── build_glpi_seed_assets.py # Reproducible GLPI downloader/transformer
│   ├── start.sh                  # Container entrypoint (starts supervisord)
│   └── healthcheck.sh            # Docker health probe (frontend and login API)
└── seed/
    ├── docker-compose.seed.yml   # Optional: local dev seed stack (not required for build)
    ├── seed-local.sh             # Optional: local seed helper (not required for build)
    ├── .env.seed                 # Seed environment (API URL, admin creds)
    └── seed_peppermint.js        # JS seeder used by build-seed.sh and seed-local.sh
```

## Compiled-bundle and ticket creation regressions

Run the compiled-bundle patch tests with Node.js, then run the browser test against
an isolated seeded container (it creates a ticket). The browser test requires
Python Playwright with Chromium:

```bash
node --test tests/test-*.cjs
python tests/smoke_new_ticket.py --url http://localhost:3000
```

The performance patch updates server and browser manifests when renaming ticket
and internal-user bundles. It also fails the image build if a client build
manifest references a missing JavaScript or CSS asset, preventing navigation
from requesting a deleted bundle and falling back to a full page reload.

The browser test checks successful creation, arrival at `/issues`, and the new
ticket's presence in the list at a 1280×720 viewport.
