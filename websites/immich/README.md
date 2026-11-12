---
title: Immich WebArena
emoji: 📷
colorFrom: blue
colorTo: green
sdk: docker
app_port: 2283
startup_duration_timeout: 30m
---

# Immich WebArena

Self-contained Immich instance for WebArena-style benchmarking. A single Docker image runs the full stack (PostgreSQL 14, Redis, immich-server, immich-ml) with pre-seeded users and photos baked in.

## Quick start (prebuilt image)

If you just want to run the environment without building from scratch:

```bash
docker pull ilboglions/immich-webarena:latest
docker run -p 2283:2283 ilboglions/immich-webarena:latest
```

Open [http://localhost:2283](http://localhost:2283) — all users, photos, and ML embeddings are already baked in. See [Credentials](#credentials) for login details.

---

## Building from scratch

The sections below describe how to rebuild the image with your own photo dataset.

### Prerequisites

- Docker — for building and running the image
- `uv` — for the download script ([install](https://docs.astral.sh/uv/))
- Node.js 20 or newer — only needed for the legacy host-side seeding script
- ~10 GB disk space (photos + Docker layers)

### Build Pipeline

The Dockerfile performs seeding during `docker build`: it starts PostgreSQL, Redis, Immich, and Immich ML inside the build container, uploads `seed/photos/`, waits for processing, and bakes both the exported reset artifacts and the already-expanded runtime state into the final image. New containers therefore skip the expensive database restore and upload/cache extraction path at startup.

If `seed/photos/` already contains reviewed photos, build directly:

```bash
docker build -t immich-webarena .
```

Then run:

```bash
docker run -p 2283:2283 immich-webarena
```

The photo directory is large, so the first build sends several GB of context and can take 30-90 minutes depending on the photo count and machine speed.

The full source-data pipeline has three stages: **download → review → build**.

#### Quick start (all defaults)

```bash
./scripts/prepare.sh
```

This downloads 300 photos per user for 5 agent accounts + admin, pauses for manual review, then builds the Docker image. Seeding happens inside the Dockerfile.

#### Custom user count and photo count

```bash
./scripts/prepare.sh --num-agents 3 --per-user 100
```

Creates: `admin`, `agent1`, `agent2`, `agent3` — 100 photos each.

#### All options

```
./scripts/prepare.sh [OPTIONS]

  --num-agents N    Number of agent users (default: 5 → agent1..agent5)
  --per-user N      Photos per user (default: 300)
  --output DIR      Photo staging directory (default: seed/photos)
  --image NAME      Docker image tag (default: immich-webarena)
  --skip-download   Skip download, use existing seed/photos/
  --skip-seed       Deprecated no-op; seeding happens inside the Dockerfile
  --skip-build      Download and review only; don't build Docker image
  --preloaded       Deprecated compatibility path; the Dockerfile now preloads runtime state
  --push REPO       Push preloaded image to Docker Hub (e.g., user/immich-webarena:latest)
```

### Step-by-step (manual)

If you prefer to run stages individually:

#### 1. Download photos

```bash
./scripts/download-photos.py --num-agents 5 --per-user 300
```

Photos land in `seed/photos/{admin,agent1,...,agent5}/`. The script streams from the Open Images V7 dataset (CC-BY 2.0) and assigns images round-robin across users.

**Options:**
- `--num-agents N` — number of agent accounts (default: 5)
- `--per-user N` — images per user (default: 300)
- `--output DIR` — output directory (default: `seed/photos`)

#### 2. Review and curate photos (REQUIRED)

> **Warning:** Photos are sourced from Open Images V7, a crowd-sourced dataset of real-world
> images. It may contain NSFW content, low-quality images, or other material you don't want
> in your benchmark environment. **You must manually review and remove unwanted images before
> seeding.** Once photos are baked into the Docker image, changing them requires a full re-seed.

After downloading, open each user's folder and **delete every image you don't want**:

```
seed/photos/
├── admin/      ← review these
├── agent1/     ← review these
├── agent2/     ← review these
├── agent3/     ← review these
├── agent4/     ← review these
└── agent5/     ← review these
```

**What to remove:**

| Category | Why |
|---|---|
| NSFW or inappropriate content | Open Images is crowd-sourced; explicit or offensive images may appear |
| Low-quality or corrupted images | Blurry, truncated, or unrecognizable photos add noise to benchmarks |
| Duplicate or near-duplicate images | Visually identical photos reduce dataset diversity |
| Personally identifiable content | Faces, license plates, addresses, or other PII may raise privacy concerns |
| Off-topic images | If you want a specific theme or distribution, remove outliers |

**How to review:**
- Open `seed/photos/` in Finder (macOS), Files (Linux), or Explorer (Windows) and use thumbnail view
- Browse each user folder (`admin/`, `agent1/`, ..., `agent5/`) individually
- Select and delete any unwanted files — there is no undo, but you can re-download with `download-photos.py`
- Each user folder is independent; you can have different photo counts per user

```bash
# Example: remove specific images
rm seed/photos/admin/oi7_000042.jpg seed/photos/agent2/oi7_001337.jpg

# Example: check remaining counts after curation
for d in seed/photos/*/; do echo "$(basename "$d"): $(find "$d" -type f | wc -l) images"; done
```

> **Note:** If you're using the **prebuilt Docker Hub image** (`docker pull ilboglions/immich-webarena`),
> photos have already been curated. This step only applies when building from scratch.

> **Tip:** If you deleted too many photos, re-run `./scripts/download-photos.py` to top up.
> It downloads fresh images without duplicating files already present.

If using `prepare.sh`, the script will automatically **pause and prompt you** at this point:

```
=== MANUAL REVIEW ===
Photos are in: seed/photos/
  admin:       300 images
  agent1:      300 images
  ...
You can now open seed/photos/ and delete any unwanted images.
When ready, press Enter to continue (or Ctrl+C to abort).
```

Only after you press Enter will the Docker build proceed with the remaining photos.

#### 3. Optional legacy host-side seed

Starts a temporary Immich docker-compose stack, creates users, uploads photos, waits for ML processing (CLIP embeddings, thumbnails), dumps the DB and upload data, then tears down. This legacy path is useful for debugging seeding outside Dockerfile builds.

```bash
# With default 5 agents:
./scripts/seed-local.sh

# With a different agent count (must match what you downloaded):
NUM_AGENTS=3 ./scripts/seed-local.sh
```

Output artifacts go to `data/`:
- `data/immich_db.sql.gz` — PostgreSQL dump
- `data/upload.tar.gz` — uploaded media + thumbnails
- `data/ml-cache.tar.gz` — CLIP model cache

> **Note:** This legacy path requires Docker Compose and Node.js 20+. The normal Dockerfile build does not require host Node.js.

#### 4. Build Docker image

```bash
docker build -t immich-webarena .
```

The Dockerfile uploads `seed/photos/`, processes them, and writes both the reset artifacts and the expanded runtime DB/upload/ML state into the image at build time. No network access or first-boot restore is needed at runtime.

#### 5. Run

```bash
docker run -p 2283:2283 immich-webarena
```

Open [http://localhost:2283](http://localhost:2283). The instance is ready when `GET /api/server/ping` returns `{"res":"pong"}`.

The compressed seed archives remain in `/seed/` so `/usr/local/bin/webarena-reset-state` can still restore a running container to the benchmark baseline.

---

## Credentials

| User    | Email                    | Password         |
|---------|--------------------------|------------------|
| Admin   | `admin@immich.local`     | `webarena_admin` |
| Agent 1 | `agent1@immich.local`    | `agent1password` |
| Agent 2 | `agent2@immich.local`    | `agent2password` |
| Agent 3 | `agent3@immich.local`    | `agent3password` |
| Agent 4 | `agent4@immich.local`    | `agent4password` |
| Agent 5 | `agent5@immich.local`    | `agent5password` |

Agent passwords follow the pattern `agent{N}password`.

---

## Re-seeding with different photos

If you want to rebuild with a different dataset, delete the old photo set and re-run:

```bash
rm -rf seed/photos/
./scripts/prepare.sh --num-agents 5 --per-user 150
```

---

## Licenses

| Component | Source | License |
|-----------|--------|---------|
| [Immich](https://github.com/immich-app/immich) | immich-app/immich | [GNU AGPL-3.0](https://github.com/immich-app/immich/blob/main/LICENSE) |
| [Open Images V7](https://storage.googleapis.com/openimages/web/index.html) (photo dataset) | [bitmind/open-images-v7](https://huggingface.co/datasets/bitmind/open-images-v7) on HuggingFace | [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/) |

> **AGPL-3.0 note:** Immich is licensed under AGPL-3.0. If you modify Immich's source and deploy it publicly (including via HF Spaces), you must make the modified source available.

---

## Architecture notes

- Base image: `debian:trixie-slim` (glibc ≥2.38 required for sharp native bindings)
- PostgreSQL 14 from PGDG apt repo (trixie ships PG17 by default)
- Python 3.11 copied from ML image (ML venv built against 3.11; trixie ships 3.13)
- All services managed by `supervisord` inside one container
- Designed for HF Spaces free tier (2 vCPU, 16 GB RAM, UID 1000, ephemeral storage)
