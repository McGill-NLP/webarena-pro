#!/bin/bash
# seed-local.sh — Spin up a temporary Penpot stack, seed it, export the DB.
#
# Run from the penpot/ directory:
#   ./scripts/seed-local.sh
#
# Output: data/penpot_db.sql.gz  (baked into the Docker image)
#
# We talk directly to the backend on port 6060, bypassing the nginx frontend.
# This avoids having to wait for nginx to be configured and healthy.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SEED_DIR="$PROJECT_DIR/seed"
DATA_DIR="$PROJECT_DIR/data"
COMPOSE_FILE="$SEED_DIR/docker-compose.seed.yml"
SEED_PY="$SEED_DIR/seed_penpot.py"
SEED_DATA="$PROJECT_DIR/seed_data.json"

source "$SEED_DIR/.env.seed"

# Detect compose command
if docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo "ERROR: Neither 'docker compose' nor 'docker-compose' found."
    exit 1
fi

cleanup() {
    echo ""
    echo "=== Shutting down seed environment ==="
    $COMPOSE_CMD -f "$COMPOSE_FILE" down -v 2>/dev/null || true
}
trap cleanup EXIT

# ── Step 1: Start Penpot ────────────────────────────────────────────────────
echo ""
echo "=== [1/6] Starting Penpot docker-compose... ==="
$COMPOSE_CMD -f "$COMPOSE_FILE" up -d

# ── Step 2: Wait for backend to be reachable on port 6060 ───────────────────
# We poll the backend directly (not via nginx) — faster and more reliable.
echo ""
echo "=== [2/6] Waiting for Penpot backend to be ready (port 6060)... ==="
for i in $(seq 1 150); do
    STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
        "$PENPOT_BACKEND_URL/api/rpc/command/get-profile" 2>/dev/null || echo "0")
    # 401 = not authenticated but server is up; 403 = same
    if [ "$STATUS" = "401" ] || [ "$STATUS" = "403" ] || [ "$STATUS" = "200" ]; then
        echo "  Backend ready after ~$((i * 2))s (HTTP $STATUS)."
        break
    fi
    if [ "$i" -eq 150 ]; then
        echo "ERROR: Penpot backend did not become ready in 300s"
        echo "--- backend logs ---"
        $COMPOSE_CMD -f "$COMPOSE_FILE" logs --tail=50 penpot-backend
        exit 1
    fi
    sleep 2
done

# ── Step 3: Run Python seeder ────────────────────────────────────────────────
echo ""
echo "=== [3/6] Running seed script... ==="
python3 "$SEED_PY" \
    --url "$PENPOT_BACKEND_URL" \
    --seed-file "$SEED_DATA" \
    --verbose

# ── Step 4: Apply team membership SQL directly ───────────────────────────────
echo ""
echo "=== [4/6] Adding team memberships via SQL... ==="
MEMBERSHIP_SQL=$(python3 "$SEED_PY" \
    --url "$PENPOT_BACKEND_URL" \
    --seed-file "$SEED_DATA" \
    --generate-sql)

DB_CONTAINER=$($COMPOSE_CMD -f "$COMPOSE_FILE" ps -q penpot-postgres)
echo "$MEMBERSHIP_SQL" | docker exec -i "$DB_CONTAINER" \
    psql -U penpot -d penpot 2>&1 | grep -v "^$" || true
echo "  Team memberships applied."

# ── Step 5: Mark onboarding as completed for all seeded users ───────────────
echo ""
echo "=== [5/7] Marking onboarding/tutorial as completed... ==="
docker exec "$DB_CONTAINER" psql -U penpot -d penpot -c "
UPDATE profile
SET props = COALESCE(props, '{}'::jsonb)
                     || jsonb_build_object(
                                '~:onboarding-viewed', true,
                                '~:viewed-tutorial?', true,
                                '~:viewed-walkthrough?', true,
                                '~:v2-info-shown', true
                            )
WHERE deleted_at IS NULL;
" >/dev/null
echo "  Onboarding flags updated for all active profiles."

# ── Step 6: Export database dump ─────────────────────────────────────────────
echo ""
echo "=== [6/7] Exporting PostgreSQL dump... ==="
mkdir -p "$DATA_DIR"

DB_CONTAINER=$($COMPOSE_CMD -f "$COMPOSE_FILE" ps -q penpot-postgres)
docker exec "$DB_CONTAINER" \
    pg_dump -U penpot --no-owner --no-privileges penpot \
    | gzip > "$DATA_DIR/penpot_db.sql.gz"

echo "  DB dump: $(du -h "$DATA_DIR/penpot_db.sql.gz" | cut -f1)"

# ── Step 7: Export assets (thumbnails, uploaded media) ───────────────────────
echo ""
echo "=== [7/7] Exporting assets directory... ==="

# Wait for Penpot's background workers to finish processing images and
# generating thumbnails (file_thumbnail, object_thumbnail, media storage).
echo "  Waiting 30s for background workers to finish processing assets..."
sleep 30

# Poll until the asset file count stabilises (no new files for 5s)
PREV_COUNT=-1
STABLE=0
while [ "$STABLE" -lt 3 ]; do
    CURR_COUNT=$(docker exec "$($COMPOSE_CMD -f "$COMPOSE_FILE" ps -q penpot-backend)" \
        find /opt/data/assets -type f 2>/dev/null | wc -l | tr -d ' ')
    if [ "$CURR_COUNT" = "$PREV_COUNT" ]; then
        STABLE=$((STABLE + 1))
    else
        STABLE=0
        PREV_COUNT="$CURR_COUNT"
    fi
    sleep 5
done
echo "  Asset count stabilised at $CURR_COUNT files."

rm -rf "$DATA_DIR/assets"
mkdir -p "$DATA_DIR/assets"
BACKEND_CONTAINER=$($COMPOSE_CMD -f "$COMPOSE_FILE" ps -q penpot-backend)
docker cp "$BACKEND_CONTAINER:/opt/data/assets/." "$DATA_DIR/assets/"
echo "  Assets exported: $(find "$DATA_DIR/assets" -type f | wc -l | tr -d ' ') files, $(du -sh "$DATA_DIR/assets" | cut -f1)"

echo ""
echo "=== Seeding complete ==="
echo "Artifacts: $DATA_DIR/penpot_db.sql.gz, $DATA_DIR/assets/"
echo ""
echo "Next step:"
echo "  docker build -t penpot-webarena $PROJECT_DIR"
echo "  docker run -p 9001:9001 penpot-webarena"
