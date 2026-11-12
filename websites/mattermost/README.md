# Mattermost Seed Data

Pre-populated Mattermost Docker image with realistic mock data for agent testing.
Data is baked into the Docker image (WebArena style) — no external volumes or seed scripts needed at runtime.

The image uses **Mattermost Team Edition 11.4.2**. The unlicensed Enterprise
binary runs as Entry Edition, whose 10,000-message history limit is incompatible
with this benchmark's larger corpus. Team Edition keeps older task evidence
available without a commercial license. See Mattermost's
[Entry and Team Edition product changes](https://mattermost.atlassian.net/wiki/spaces/DES/pages/3770482692/Entry+and+Team+Edition+Product+Changes+-+Base+Scope).
This changes the server distribution; it does not delete messages, move their
timestamps, or change task-user memberships.

The Dockerfile verifies the official Team release archives with SHA-256 pins
for both amd64 and arm64. When changing `MATTERMOST_VERSION`, update the matching
`MATTERMOST_TEAM_SHA256_AMD64` and `MATTERMOST_TEAM_SHA256_ARM64` arguments from
Mattermost's [release archive](https://docs.mattermost.com/product-overview/version-archive)
and the release files named `mattermost-team-VERSION-linux-ARCH.tar.gz.sha256`.
Rebuild and deploy the image to apply the edition change; resetting an older
container only restores its database and does not replace its server binary.

## Quick Start

```bash
# Build the image (one time)
cd mattermost
docker build -t mattermost-populated .

# Run
docker run -d --name mattermost -p 8065:8065 mattermost-populated

# Reset (wipe all changes, back to clean state)
docker rm -f mattermost
docker run -d --name mattermost -p 8065:8065 mattermost-populated
```

Access Mattermost at **http://localhost:8065**

To exercise Calls with a directly launched container, also configure the media
ports and advertised address shown in [Native Calls and task 109](#native-calls-and-task-109).

### Credentials

| Role | Username | Password |
|------|----------|----------|
| Admin | `admin` | `Admin@Secure123` |
| Any regular user | `john.doe`, `jane.smith`, etc. | `User@Secure123` |

## How It Works

The Docker image contains everything: Mattermost server, PostgreSQL database, and all mock data pre-loaded. This follows the same pattern as WebArena:

```bash
# WebArena shopping site
docker run --name shopping -p 7770:80 -d shopping_final_0712

# Our Mattermost
docker run --name mattermost -p 8065:8065 -d mattermost-populated
```

**Reset = `docker rm -f` + `docker run`** — each `docker run` starts from the original baked-in data. Any changes made during testing are discarded.

## What's Included

### Users (16 total)

| Username | Role | Team |
|----------|------|------|
| `admin` | System Administrator | All |
| `john.doe` | Engineering Manager | Engineering, General |
| `jane.smith` | Senior Developer | Engineering, General |
| `bob.wilson` | DevOps Engineer | Engineering, General |
| `alice.johnson` | Frontend Developer | Engineering, General |
| `charlie.brown` | Backend Developer | Engineering, General |
| `diana.prince` | QA Engineer | Engineering, General |
| `kevin.martinez` | Product Manager | Engineering, Marketing, General |
| `lisa.wang` | Security Engineer | Engineering, General |
| `mike.ross` | Junior Developer | Engineering, General |
| `natalie.kim` | Technical Writer | Engineering, General |
| `emma.davis` | Marketing Manager | Marketing, General |
| `frank.miller` | Content Writer | Marketing, General |
| `grace.lee` | UI/UX Designer | Marketing, General |
| `ivy.chen` | Data Analyst | Marketing, General |
| `henry.taylor` | HR Manager | General |

### Teams (3)

- **Engineering** — Software Engineering team (10 members)
- **Marketing** — Marketing and Growth team (5 members)
- **TechCorp General** — Company-wide hub (all 16 members)

### Channels (44 custom channels; 50 visible team channels total)

**Engineering (9 channels):** `project-alpha`, `project-beta`, `deployments`, `code-reviews`, `bugs-and-issues`, `standup-notes`, `tech-discussions`, `devops`, `security-alerts` (private)

**Dataset-backed Engineering (24 channels):** `python-web-services`, `python-data-science`, `python-packaging`, `python-async-concurrency`, `python-testing`, `python-language`, `clojurescript-frontend`, `clojure-web-services`, `clojure-data-systems`, `clojure-build-tools`, `clojure-concurrency`, `clojure-language`, `elm-architecture`, `elm-ui-styling`, `elm-http-json`, `elm-routing`, `elm-build-tools`, `elm-language`, `racket-macros`, `racket-gui-graphics`, `racket-data-structures`, `racket-web-services`, `racket-packages`, `racket-language`

**Marketing (5 channels):** `campaigns`, `social-media`, `analytics`, `content-calendar`, `design-requests`

**General (6 channels):** `announcements`, `random`, `watercooler`, `events`, `help-desk`, `new-joiners`

Mattermost also creates `town-square` and `off-topic` in each team, bringing the visible team-channel count to exactly 50. Direct and group-message channels are not included in that count.

### Conversations

- **218 original mock posts** plus **31,615 imported dataset messages** with threaded replies
- **6 direct message conversations** between pairs of users
- **2 group message conversations**
- **Pinned posts** in announcements, events, and onboarding channels
- Topics: sprint planning, deployments, code reviews, bug reports, security incidents, marketing campaigns, analytics, casual chat

## Dataset-backed channel corpus

The 24 additional Engineering channels and the 20 original custom channels use message text copied verbatim from [Software-related Slack Chats with Disentangled Conversations](https://github.com/preethac/Software-related-Slack-Chats-with-Disentangled-Conversations). Each added channel contains at least 1,000 messages, and every original channel has an additional 250–528 topic-matched messages. Whole disentangled conversations are retained as Mattermost threads. Because the dataset participant names are anonymized and do not exist in this Mattermost instance, the builders deterministically map them onto seeded team users without changing message text.

Rebuild the supplemental seed after cloning the source dataset:

```bash
python scripts/build_slack_channel_seed.py /path/to/Software-related-Slack-Chats-with-Disentangled-Conversations
python scripts/build_existing_channel_backfill.py /path/to/Software-related-Slack-Chats-with-Disentangled-Conversations
python scripts/build_task_message_evidence.py
```

Apply only the supplemental channels and corpus to an already seeded instance:

```bash
python seed_mattermost.py \
  --url http://localhost:8065 \
  --seed-file slack_channel_seed.json \
  --workers 24

python seed_mattermost.py \
  --url http://localhost:8065 \
  --seed-file existing_channel_backfill_seed.json \
  --workers 20

docker exec -i mattermost psql -U mmuser -d mattermost_test \
  < scripts/finalize_task_ready_seed.sql

python scripts/verify_task_ready_seed.py
```

The channel and user creation steps are idempotent, but post creation is not. Apply each supplemental seed only once to a given database. The finalization script assigns source dates to the original-channel backfill, preserves all protected task-message timestamps and ranks, leaves the admin task user in 14 team channels (17 conversations including DM/GMs), and establishes exactly 8 unread messages.

## Task-message evidence

[`TASK_MESSAGE_EVIDENCE.md`](TASK_MESSAGE_EVIDENCE.md) indexes all 38 canonical Mattermost/cross-site tasks and 10 legacy Mattermost tasks. [`task_message_evidence.csv`](task_message_evidence.csv) is the canonical exact table, including task IDs, source positions, sites, intents, current hints, exact supporting message text, post IDs, timestamps, newest-first ranks, and hashes. [`protected_task_messages.json`](protected_task_messages.json) is the machine-readable preservation manifest used for verification.

## History-access regression

Run the live check against a newly built image:

```bash
uv run --with requests --with playwright python -m playwright install chromium
uv run --with requests --with playwright python scripts/verify_history_access.py \
  --image mattermost-populated --artifacts-dir /tmp/mattermost-history-check
```

The check creates its own Docker container with a random loopback port, a 1.5 CPU
limit and 3 GiB memory limit, and removes it on completion. It never resets an
existing deployment. It checks Team Edition, the current SQL seed's 31,834 user
posts (31,830 undeleted and 4 already deleted), all 19 protected evidence records (including E19's
Emma DM), and the intentional admin seed of 14 team channels, 17 conversations,
and 8 unread messages. The full message fingerprint must match after reset.

Chromium logs in through the UI, searches for `authentication` and opens its
thread to read the task100 deadline reply E02 (whose own wording is "auth flow").
It also searches E02 directly and deployment schedule E01, opens the posts, and
reads Emma's existing DM with an editable composer. It checks that no Restore Access prompt
appears. After adding a disposable post, it invokes the native reset in its own
container and repeats every check. Screenshots, a JSON report, and container logs
are saved to the selected artifact directory; do not commit them. Current
`task137` asks for a new DM to Emma, so the Emma check covers access to its contact
and composer, not completion of that multi-site task.

## Scenarios for Agent Testing

| Scenario | Example Task |
|----------|-------------|
| Information retrieval | "What is the deployment schedule for this week?" |
| Search across channels | "Find all messages about the Safari bug" |
| User lookup | "Who is the DevOps engineer?" |
| Channel management | "Create a new channel for Project Gamma" |
| Post creation | "Post the standup update in standup-notes" |
| Thread replies | "Reply to Bob's deployment notice with approval" |
| Cross-referencing | "What security issues were discussed this week?" |
| DM conversations | "Send a message to Jane about the code review" |
| Analytics queries | "What were the Q1 campaign results?" |
| Status checks | "Is there a planned deployment tonight?" |

## Adding More Mock Data

To add more data, you need to: edit `seed_data.json`, re-seed a temporary container, export the database, and rebuild the image.

### Step 1: Edit `seed_data.json`

#### Add users
```json
{
  "username": "new.user",
  "password": "User@Secure123",
  "email": "new.user@techcorp.com",
  "first_name": "New",
  "last_name": "User",
  "nickname": "newu",
  "position": "Software Engineer"
}
```
Then add the username to the `"members"` list of the relevant teams.

#### Add teams
```json
{
  "name": "data-science",
  "display_name": "Data Science",
  "description": "Data Science and ML team",
  "type": "O",
  "members": ["ivy.chen", "new.user"]
}
```

#### Add channels
Add to the `"channels"` object under the team name:
```json
"data-science": [
  {
    "name": "ml-experiments",
    "display_name": "ML Experiments",
    "purpose": "Discuss ML model experiments and results",
    "header": "Current experiment: Customer churn prediction v3",
    "type": "O"
  }
]
```

#### Add conversations
```json
"data-science": {
  "ml-experiments": [
    {
      "user": "ivy.chen",
      "message": "Started training the new churn prediction model.",
      "pin": false,
      "replies": [
        {"user": "new.user", "message": "What's the baseline accuracy?"}
      ]
    }
  ]
}
```

#### Add direct messages
```json
{
  "participants": ["ivy.chen", "new.user"],
  "messages": [
    {"user": "ivy.chen", "message": "Hey, can you review my model notebook?"},
    {"user": "new.user", "message": "Sure, send me the link!"}
  ]
}
```

### Step 2: Rebuild the image

```bash
cd mattermost

# Start a temporary container from the base image
docker run -d --name mm-temp -p 8065:8065 mattermost/mattermost-preview:latest

# Wait for it to start (~15s)
# Seed with updated data
conda activate webarena-pro
python seed_mattermost.py --url http://localhost:8065

# Export the database
docker exec mm-temp bash -c "su - postgres -c 'pg_dump -U mmuser mattermost_test'" > mattermost_seed.sql

# Clean up temp container
docker rm -f mm-temp

# Rebuild the baked image
docker build -t mattermost-populated .

# Test it
docker run -d --name mattermost -p 8065:8065 mattermost-populated
```

## File Structure

```
mattermost/
├── README.md                 # This file
├── Dockerfile                # Builds the baked Docker image
├── docker-entry-seeded.sh    # Container entrypoint (starts PostgreSQL + Mattermost)
├── mattermost_seed.sql       # PostgreSQL dump with all mock data (baked into image)
├── seed_data.json            # Mock data definitions (source of truth for re-seeding)
├── slack_channel_seed.json   # Generated 24-channel dataset supplement
├── existing_channel_backfill_seed.json # Generated corpus for the original channels
├── TASK_MESSAGE_EVIDENCE.md  # Human-readable task/evidence index
├── task_message_evidence.csv # Canonical exact evidence table
├── protected_task_messages.json # Machine-readable preservation manifest
├── seed_mattermost.py        # Python seeder script (used during image build)
├── scripts/
│   ├── build_slack_channel_seed.py
│   ├── build_existing_channel_backfill.py
│   ├── build_task_message_evidence.py
│   ├── finalize_task_ready_seed.sql
│   └── verify_task_ready_seed.py
└── requirements.txt          # Python dependencies (requests)
```

## Conda Environment

```bash
# Already exists (Python 3.11 + requests)
conda activate webarena-pro

# If you need to recreate:
conda create -n webarena-pro python=3.11 -y
conda activate webarena-pro
pip install -r requirements.txt
```

## Troubleshooting

**Mattermost takes a while to start:**
- The server needs ~15-20 seconds after `docker run` to fully initialize.
- Check readiness: `curl http://localhost:8065/api/v4/system/ping`

**Docker permission issues:**
- Your user needs to be in the `docker` group.
- Quick fix: prefix commands with `sg docker -c "..."` or run `newgrp docker`.

**Port conflicts:**
- Mattermost uses port 8065. Change with: `docker run -p 9065:8065 ...`

## Native Calls and task 109

The official Team Edition arm64 server archive omits prepackaged plugins. The
Dockerfile adds the official Calls 1.11.0 arm64 archive and signature, each
verified against a SHA-256 pin, to match the Calls version bundled with amd64.
When updating Mattermost or Calls, verify compatibility and update both plugin
pins from the [official release assets](https://github.com/mattermost/mattermost-plugin-calls/releases/tag/v1.11.0).

The image enables the bundled Mattermost Calls plugin, including direct-message
ringing and its integrated RTC service. It does not need an external RTCD service
or STUN server for local workers. A browser with no microphone can join muted;
the benchmark does not grant microphone permissions or add fake media devices.

Task 109 retains its original intent: "Call Emma and Bob. If no one joins within
30 seconds, end the call and send them a direct message asking them to call back
when they’re available." The supported Team Edition workflow calls Emma Davis
and Bob Wilson separately, waits at least 30 seconds in each unanswered call,
ends each call, and sends each person a callback DM. The grader checks this
workflow with three equally weighted, independent partial-credit nodes.
[Mattermost Team Edition supports one-to-one calls](https://docs.mattermost.com/deployment-guide/calls/calls-deployment-guide);
group calls require a paid edition. No license override is enabled.

Core publishes a separate TCP/UDP RTC port for each worker and advertises it to
the browser. The entrypoint binds the RTC service to the container's first
non-loopback IPv4 interface when an advertised host is configured. This avoids
duplicate loopback/network ICE candidates behind Docker NAT. Explicit native
UDP/TCP bind addresses remain supported. Remote browsers need a reachable
advertised address and media port in addition to a secure HTTP origin.

The grader reads existing channels, exact DM membership, native call records,
and saved messages without creating channels. Evidence must belong to the
current execution; older callers with only a task date use that UTC day boundary.
Call duration is checked from the same native post's millisecond start/end times.
The bundled Calls 1.11 plugin has an upstream bug that writes null participant
lists to ended posts. The fixed official Calls releases require Mattermost 12
([Calls 1.12.6 release](https://github.com/mattermost/mattermost-plugin-calls/releases/tag/v1.12.6)). Missing or short calls still fail deterministically, but
when both durations are established and participant metadata is unavailable,
the participant criterion uses the existing semantic judge on the observed
call history. Null never means that nobody joined. Callback wording is also
judged semantically, after verifying actual saved messages to both exact peers.

Reset stops Mattermost and Calls before restoring PostgreSQL and files. PID 1
acknowledges that the application has stopped, then waits until restore completes
before restarting it. A failed PostgreSQL stop leaves the application stopped
and refuses to overwrite the database. Readiness includes the native Calls
plugin endpoint.

### Calls regression check

Use a disposable image/container, explicit loopback HTTP and matching TCP/UDP
media bindings, and an ownership label. Do not run this against a shared worker.
For example, after building the image:

~~~bash
docker run -d --name mattermost-calls-test --label webarena.calls-test=true \
  --cpus 2 --memory 4g \
  -p 127.0.0.1:18065:8065 \
  -p 127.0.0.1:18443:8443/tcp -p 127.0.0.1:18443:8443/udp \
  -e MM_CALLS_ICE_HOST_OVERRIDE=127.0.0.1 \
  -e MM_CALLS_ICE_HOST_PORT_OVERRIDE=18443 mattermost-populated

python scripts/verify_calls.py --url http://127.0.0.1:18065 \
  --expected-rtc-port 18443 --output /tmp/mattermost-calls-check \
  --reset-container mattermost-calls-test \
  --reset-label webarena.calls-test=true --delay-supervisor
~~~

Choose unused ports. Wait for Docker health to become healthy before running the
script. The script needs requests, Playwright, and its Chromium browser. It
uses normal browser defaults, verifies a connected and nominated ICE candidate
at the published host/port, checks active native sessions throughout both
30-second waits, ends calls through the UI, and verifies saved callbacks.
The optional reset interrupts another active call, deliberately delays PID 1
to test the reset handshake, checks that PID 1 survives while the application
PID changes, then repeats both complete flows after reset. Screenshots and logs
stay in the specified output directory. This script validates the workflow and
backend evidence; it does not invoke a paid semantic judge.
