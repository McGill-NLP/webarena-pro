#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SEED_DIR="$PROJECT_DIR/seed"
DATA_DIR="$PROJECT_DIR/data"
COMPOSE_FILE="$SEED_DIR/docker-compose.seed.yml"

# Number of agent users (agent1..agentN). Override via: NUM_AGENTS=3 ./scripts/seed-local.sh
NUM_AGENTS="${NUM_AGENTS:-5}"

# Build user list: admin + agent1..agentN
AGENT_USERS=""
for _i in $(seq 1 "$NUM_AGENTS"); do
    AGENT_USERS="$AGENT_USERS agent$_i"
done
ALL_USERS="admin$AGENT_USERS"

# Detect compose command: "docker compose" (plugin) or "docker-compose" (standalone)
if docker compose version &>/dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo "ERROR: Neither 'docker compose' nor 'docker-compose' found."
    exit 1
fi

# @immich/cli uses the global File API, which is available in Node 20+.
if ! command -v node >/dev/null 2>&1; then
    echo "ERROR: Node.js 20 or newer is required for @immich/cli."
    exit 1
fi
NODE_MAJOR=$(node -p 'Number(process.versions.node.split(".")[0])')
if [ "$NODE_MAJOR" -lt 20 ]; then
    echo "ERROR: Node.js 20 or newer is required for @immich/cli; found $(node --version)."
    echo "Install Node 20+ and rerun this script."
    exit 1
fi

# Load seed env
source "$SEED_DIR/.env.seed"

# Check for photos (expects per-user subdirs: photos/admin/, photos/agent1/, etc.)
PHOTO_COUNT=$(find "$SEED_DIR/photos" -type f \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" -o -name "*.heic" -o -name "*.webp" -o -name "*.gif" -o -name "*.mp4" -o -name "*.mov" \) 2>/dev/null | wc -l | tr -d ' ')
if [ "$PHOTO_COUNT" -eq 0 ]; then
    echo "ERROR: No photos found in $SEED_DIR/photos/"
    echo "Run 'python scripts/download-photos.py' first, or place photos in per-user subdirs:"
    echo "  seed/photos/admin/  seed/photos/agent1/  ...  seed/photos/agent5/"
    exit 1
fi
echo "Found $PHOTO_COUNT media files across user folders."

# Step 1: Start Immich
echo ""
echo "=== [1/7] Starting Immich docker-compose... ==="
$COMPOSE_CMD -f "$COMPOSE_FILE" up -d

# Step 2: Wait for server
echo ""
echo "=== [2/7] Waiting for Immich server to be ready... ==="
for i in $(seq 1 120); do
    if curl -sf http://localhost:2283/api/server/ping > /dev/null 2>&1; then
        echo "  Server ready after ${i}s."
        break
    fi
    if [ "$i" -eq 120 ]; then
        echo "ERROR: Immich server did not become ready in 240s"
        $COMPOSE_CMD -f "$COMPOSE_FILE" logs immich-server
        exit 1
    fi
    sleep 2
done

# Step 3: Create admin user
echo ""
echo "=== [3/7] Creating admin user... ==="
SIGNUP_RESP=$(curl -sf -X POST http://localhost:2283/api/auth/admin-sign-up \
    -H "Content-Type: application/json" \
    -d "{
        \"email\": \"$ADMIN_EMAIL\",
        \"password\": \"$ADMIN_PASSWORD\",
        \"name\": \"$ADMIN_NAME\"
    }" 2>&1) || true
echo "  Admin signup response: $SIGNUP_RESP"

# Step 3b: Create agent users (via admin API)
echo ""
echo "=== [3b/7] Creating agent users (NUM_AGENTS=$NUM_AGENTS)... ==="
# Login as admin first to get a token for user creation
ADMIN_LOGIN=$(curl -sf -X POST http://localhost:2283/api/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}")
ADMIN_TOKEN=$(echo "$ADMIN_LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['accessToken'])")

for i in $(seq 1 "$NUM_AGENTS"); do
    AGENT_RESP=$(curl -sf -X POST http://localhost:2283/api/admin/users \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -d "{
            \"email\": \"agent${i}@immich.local\",
            \"password\": \"agent${i}password\",
            \"name\": \"Agent ${i}\",
            \"shouldChangePassword\": false
        }" 2>&1) || true
    echo "  Created agent${i}@immich.local"
done

# Step 4: Login and get API key for admin
echo ""
echo "=== [4/7] Obtaining API keys... ==="
# Server may restart during geodata import (OOM). Retry login until it sticks.
ACCESS_TOKEN=""
for attempt in $(seq 1 60); do
    ADMIN_LOGIN=$(curl -sf -X POST http://localhost:2283/api/auth/login \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" 2>/dev/null) || true
    if [ -n "$ADMIN_LOGIN" ]; then
        ACCESS_TOKEN=$(echo "$ADMIN_LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin).get('accessToken',''))" 2>/dev/null) || true
        if [ -n "$ACCESS_TOKEN" ]; then
            break
        fi
    fi
    if [ "$attempt" -eq 60 ]; then
        echo "ERROR: Could not login to Immich server after 60 attempts"
        exit 1
    fi
    echo "  Waiting for server (attempt $attempt)..."
    sleep 5
done
echo "  Admin login OK."

# Helper: retry a curl call until it succeeds (server may restart mid-request)
api_call() {
    local result=""
    for _retry in $(seq 1 30); do
        result=$(curl -sf "$@" 2>/dev/null) || true
        if [ -n "$result" ]; then
            echo "$result"
            return 0
        fi
        sleep 5
    done
    echo "ERROR: API call failed after 30 retries: curl $*" >&2
    return 1
}

API_KEY_RESP=$(api_call -X POST http://localhost:2283/api/api-keys \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d '{"name":"seed-key","permissions":["all"]}')
ADMIN_API_KEY=$(echo "$API_KEY_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['secret'])")
echo "  Admin API key: ${ADMIN_API_KEY:0:8}..."

# Get API keys for each agent user (use named vars — bash 3 has no associative arrays)
API_KEY_admin="$ADMIN_API_KEY"

for i in $(seq 1 "$NUM_AGENTS"); do
    AGENT_LOGIN=$(api_call -X POST http://localhost:2283/api/auth/login \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"agent${i}@immich.local\",\"password\":\"agent${i}password\"}")
    AGENT_TOKEN=$(echo "$AGENT_LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['accessToken'])")

    AGENT_KEY_RESP=$(api_call -X POST http://localhost:2283/api/api-keys \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $AGENT_TOKEN" \
        -d '{"name":"seed-key","permissions":["all"]}')
    AGENT_KEY=$(echo "$AGENT_KEY_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['secret'])")
    eval "API_KEY_agent${i}=\"$AGENT_KEY\""
    echo "  agent${i} API key: ${AGENT_KEY:0:8}..."
done

# Step 5: Upload photos per user
echo ""
echo "=== [5/7] Uploading photos via immich CLI (per user)... ==="
for user in $ALL_USERS; do
    USER_DIR="$SEED_DIR/photos/$user"
    if [ ! -d "$USER_DIR" ] || [ -z "$(ls -A "$USER_DIR" 2>/dev/null)" ]; then
        echo "  Skipping $user (no photos in $USER_DIR)"
        continue
    fi
    PHOTO_NUM=$(find "$USER_DIR" -type f | wc -l | tr -d ' ')
    echo "  Uploading $PHOTO_NUM photos for $user..."
    eval "USER_KEY=\$API_KEY_${user}"
    npx --yes @immich/cli@2.5.6 upload \
        --key "$USER_KEY" \
        --url http://localhost:2283/api \
        -r "$USER_DIR/"
done

# Step 6: Wait for ML processing
echo ""
echo "=== [6/7] Waiting for ML jobs to complete... ==="
sleep 10
ATTEMPTS=0
MAX_ATTEMPTS=120  # 30 min max
while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    JOBS=$(curl -sf -H "Authorization: Bearer $ACCESS_TOKEN" \
        http://localhost:2283/api/jobs 2>/dev/null || echo "{}")
    ACTIVE=$(echo "$JOBS" | python3 -c "
import sys, json
try:
    jobs = json.load(sys.stdin)
    active = sum(
        j.get('jobCounts',{}).get('active',0) + j.get('jobCounts',{}).get('waiting',0)
        for j in jobs.values()
    )
    print(active)
except:
    print(-1)
" 2>/dev/null || echo "-1")

    if [ "$ACTIVE" = "0" ]; then
        echo "  All ML jobs complete."
        break
    fi
    if [ "$ACTIVE" = "-1" ]; then
        echo "  Could not query jobs, retrying..."
    else
        echo "  $ACTIVE jobs remaining..."
    fi
    ATTEMPTS=$((ATTEMPTS + 1))
    sleep 15
done

if [ $ATTEMPTS -ge $MAX_ATTEMPTS ]; then
    echo "WARNING: Timed out waiting for ML jobs. Proceeding with export anyway."
fi

# Step 6b: Disable onboarding and password-change prompts
echo ""
echo "=== [6b/7] Disabling onboarding & password-change prompts... ==="
CONTAINER_DB=$($COMPOSE_CMD -f "$COMPOSE_FILE" ps -q database)
docker exec "$CONTAINER_DB" psql -U postgres -d immich -c \
    "INSERT INTO system_metadata (key, value) VALUES ('admin-onboarding', '{\"isOnboarded\": true}') ON CONFLICT (key) DO UPDATE SET value = '{\"isOnboarded\": true}';"
docker exec "$CONTAINER_DB" psql -U postgres -d immich -c \
    "UPDATE \"user\" SET \"shouldChangePassword\" = false;"
docker exec "$CONTAINER_DB" psql -U postgres -d immich -c \
    "INSERT INTO user_metadata (\"userId\", key, value) SELECT id, 'preferences', '{\"onboarding\": {\"isOnboarded\": true}}' FROM \"user\" ON CONFLICT (\"userId\", key) DO UPDATE SET value = user_metadata.value || '{\"onboarding\": {\"isOnboarded\": true}}'::jsonb;"
echo "  Onboarding marked complete, shouldChangePassword disabled for all users."

# Step 7: Export data
echo ""
echo "=== [7/7] Exporting seeded data... ==="
mkdir -p "$DATA_DIR"

# DB dump (plain SQL, no owner info, gzipped)
CONTAINER_DB=$($COMPOSE_CMD -f "$COMPOSE_FILE" ps -q database)
docker exec "$CONTAINER_DB" pg_dump -U postgres --no-owner --no-privileges immich | gzip > "$DATA_DIR/immich_db.sql.gz"
echo "  DB dump: $(du -h "$DATA_DIR/immich_db.sql.gz" | cut -f1)"

# Upload directory
CONTAINER_SERVER=$($COMPOSE_CMD -f "$COMPOSE_FILE" ps -q immich-server)
TMP_EXPORT="/tmp/immich-upload-export-$$"
mkdir -p "$TMP_EXPORT"
docker cp "$CONTAINER_SERVER":/data/. "$TMP_EXPORT/"
tar czf "$DATA_DIR/upload.tar.gz" -C "$TMP_EXPORT" .
rm -rf "$TMP_EXPORT"
echo "  Upload archive: $(du -h "$DATA_DIR/upload.tar.gz" | cut -f1)"

# ML model cache
CONTAINER_ML=$($COMPOSE_CMD -f "$COMPOSE_FILE" ps -q immich-machine-learning)
TMP_CACHE="/tmp/immich-ml-cache-$$"
mkdir -p "$TMP_CACHE"
docker cp "$CONTAINER_ML":/cache/. "$TMP_CACHE/"
tar czf "$DATA_DIR/ml-cache.tar.gz" -C "$TMP_CACHE" .
rm -rf "$TMP_CACHE"
echo "  ML cache: $(du -h "$DATA_DIR/ml-cache.tar.gz" | cut -f1)"

# Shutdown
echo ""
echo "=== Shutting down seeding environment... ==="
$COMPOSE_CMD -f "$COMPOSE_FILE" down -v

echo ""
echo "=== Seeding complete ==="
echo "Artifacts in $DATA_DIR/:"
ls -lh "$DATA_DIR/"
echo ""
echo "Next steps:"
echo "  docker build -t immich-webarena $PROJECT_DIR"
echo "  docker run -p 2283:2283 immich-webarena"
