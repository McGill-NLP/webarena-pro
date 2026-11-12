#!/usr/bin/env bash
# seed-local.sh — Generate a seeded Peppermint DB dump for baking into the Docker image.
#
# What it does:
#   1. Spins up a temporary Peppermint + PostgreSQL stack
#   2. Waits for the Fastify API to respond (checked from INSIDE the container,
#      since Fastify binds to 127.0.0.1 and is not reachable from the host)
#   3. Copies the Node.js seeder + seed_data.json into the container and runs it
#   4. Exports a gzip-compressed PostgreSQL dump to data/peppermint_db.sql.gz
#   5. Tears down the temporary stack
#
# After this script completes, run:
#   docker build -t peppermint-webarena .
#
# Requirements: docker compose (v2 plugin) or docker-compose (v1 standalone)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."
COMPOSE_FILE="$ROOT/seed/docker-compose.seed.yml"
OUTPUT="$ROOT/data/peppermint_db.sql.gz"

# Support both `docker compose` (plugin) and `docker-compose` (standalone)
if docker compose version &>/dev/null 2>&1; then
    DC="docker compose"
else
    DC="docker-compose"
fi

# Cleanup on exit
cleanup() {
    echo ""
    echo "Tearing down temporary seed stack..."
    $DC -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

# ── Step 1: Start the temporary stack ────────────────────────────────────────
echo "==> Starting temporary Peppermint stack for seeding..."
$DC -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
$DC -f "$COMPOSE_FILE" up -d

# Resolve the actual container name
CONTAINER=$($DC -f "$COMPOSE_FILE" ps -q peppermint)
if [ -z "$CONTAINER" ]; then
    echo "ERROR: Could not find Peppermint container."
    exit 1
fi
echo "  Container: $CONTAINER"

# ── Step 2: Wait for the Fastify API ─────────────────────────────────────────
# Fastify binds to 127.0.0.1:5003 inside the container, so we must poll from
# inside via `docker exec` — plain curl from the host will never reach it.
echo "==> Waiting for Peppermint API (checked from inside container)..."
TIMEOUT=180
ELAPSED=0
until STATUS=$(docker exec "$CONTAINER" sh -c 'curl -s -o /dev/null -w "%{http_code}" http://localhost:5003/ || echo 0' 2>/dev/null) \
    && [ "$STATUS" != "0" ] && [ "$STATUS" -lt 500 ] 2>/dev/null; do
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo "ERROR: API not ready after ${TIMEOUT}s. Container logs:"
        $DC -f "$COMPOSE_FILE" logs --tail=40 peppermint
        exit 1
    fi
    echo "  Still waiting... (${ELAPSED}s)"
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done
echo "  API is up."

# Give Prisma seed a moment to finish
echo "==> Waiting for Prisma seed to settle..."
sleep 8

# ── Step 3: Run the Node.js seeder inside the container ──────────────────────
echo "==> Copying seeder into container..."
docker cp "$ROOT/seed/seed_peppermint.js" "$CONTAINER:/tmp/seed_peppermint.js"
docker cp "$ROOT/seed_data.json"          "$CONTAINER:/tmp/seed_data.json"
docker cp "$ROOT/data/glpi_tickets.json" "$CONTAINER:/tmp/glpi_tickets.json"

echo "==> Running seeder..."
docker exec \
    -e PEPPERMINT_URL=http://localhost:5003 \
    -e ADMIN_EMAIL=admin@admin.com \
    -e ADMIN_PASSWORD=1234 \
    -e SEED_DATA_FILE=/tmp/seed_data.json \
    -e SEED_EXPANSION_FILES=/tmp/glpi_tickets.json \
    "$CONTAINER" node /tmp/seed_peppermint.js

echo "==> Seeding complete."

# ── Step 4: Export PostgreSQL dump ───────────────────────────────────────────
echo "==> Exporting PostgreSQL dump..."
mkdir -p "$ROOT/data"

$DC -f "$COMPOSE_FILE" exec -T peppermint_postgres \
    pg_dump -U peppermint -d peppermint --no-owner --no-acl \
    | gzip > "$OUTPUT"

DUMP_SIZE=$(wc -c < "$OUTPUT")
echo "  Dump written to data/peppermint_db.sql.gz (${DUMP_SIZE} bytes)"

if [ "$DUMP_SIZE" -lt 1000 ]; then
    echo "ERROR: Dump is suspiciously small — seeding may have failed."
    exit 1
fi

echo ""
echo "Done! You can now build the image:"
echo "  docker build -t peppermint-webarena ."
