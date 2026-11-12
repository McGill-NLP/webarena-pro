#!/bin/bash
set -euo pipefail

PG_BIN="/usr/lib/postgresql/14/bin"
PG_DATA="/var/lib/postgresql/14/data"
SEED_DIR="/seed"
PHOTO_DIR="$SEED_DIR/photos"

source "$SEED_DIR/.env.seed"

cleanup() {
    pkill -TERM -f "/usr/src/app/server/bin/start.sh" 2>/dev/null || true
    pkill -TERM -f "python -m immich_ml" 2>/dev/null || true
    pkill -TERM -f "redis-server" 2>/dev/null || true
    if [ -f "$PG_DATA/postmaster.pid" ]; then
        runuser -u user -- "$PG_BIN/pg_ctl" -D "$PG_DATA" stop -m fast >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

echo "[build-seed] Checking photos in $PHOTO_DIR"
PHOTO_COUNT=$(find "$PHOTO_DIR" -type f \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" -o -name "*.heic" -o -name "*.webp" -o -name "*.gif" -o -name "*.mp4" -o -name "*.mov" \) 2>/dev/null | wc -l | tr -d ' ')
if [ "$PHOTO_COUNT" -eq 0 ]; then
    echo "ERROR: No photos found in $PHOTO_DIR"
    exit 1
fi
echo "[build-seed] Found $PHOTO_COUNT media files"

AGENT_USERS=""
for user_dir in "$PHOTO_DIR"/agent*; do
    [ -d "$user_dir" ] || continue
    AGENT_USERS="$AGENT_USERS $(basename "$user_dir")"
done
ALL_USERS="admin$AGENT_USERS"

echo "[build-seed] Initializing PostgreSQL"
rm -rf "$PG_DATA"
mkdir -p "$PG_DATA" /data /cache /var/run/postgresql /var/run/redis /var/log/supervisor
chown -R user:user "$PG_DATA" /data /cache /var/run/postgresql /var/run/redis /var/log/supervisor
runuser -u user -- "$PG_BIN/initdb" -D "$PG_DATA" --username=user --encoding=UTF8 --locale=C
runuser -u user -- "$PG_BIN/pg_ctl" -D "$PG_DATA" \
    -o "-c config_file=/etc/postgresql/postgresql.conf -c hba_file=/etc/postgresql/pg_hba.conf" \
    -l /var/log/supervisor/pg-build-seed.log start

for _i in $(seq 1 60); do
    if "$PG_BIN/pg_isready" -U user -h localhost -q 2>/dev/null; then
        break
    fi
    sleep 1
done

runuser -u user -- "$PG_BIN/createdb" -U user immich
runuser -u user -- "$PG_BIN/psql" -U user -d immich -c "CREATE EXTENSION IF NOT EXISTS vector;"
runuser -u user -- "$PG_BIN/psql" -U user -d immich -c "CREATE EXTENSION IF NOT EXISTS vchord;"
runuser -u user -- "$PG_BIN/psql" -U user -d immich -c "CREATE EXTENSION IF NOT EXISTS vectors;"

echo "[build-seed] Starting Redis, ML, and Immich"
runuser -u user -- redis-server --port 6379 --bind 127.0.0.1 --daemonize no --dir /tmp >/var/log/supervisor/redis-build-seed.log 2>&1 &
runuser -u user -- bash -lc 'cd /usr/src && DEVICE=cpu python -m immich_ml' >/var/log/supervisor/immich-ml-build-seed.log 2>&1 &
runuser -u user -- bash -lc 'cd /usr/src/app && IMMICH_WORKERS_INCLUDE=microservices IMMICH_PORT=2284 /usr/src/app/server/bin/start.sh' >/var/log/supervisor/immich-microservices-build-seed.log 2>&1 &
runuser -u user -- bash -lc 'cd /usr/src/app && IMMICH_WORKERS_INCLUDE=api IMMICH_PORT=2283 /usr/src/app/server/bin/start.sh' >/var/log/supervisor/immich-api-build-seed.log 2>&1 &

echo "[build-seed] Waiting for Immich API"
for i in $(seq 1 180); do
    if curl -sf http://localhost:2283/api/server/ping >/dev/null 2>&1; then
        echo "[build-seed] API ready after ${i}s"
        break
    fi
    if [ "$i" -eq 180 ]; then
        echo "ERROR: Immich API did not become ready"
        tail -200 /var/log/supervisor/immich-api-build-seed.log || true
        tail -200 /var/log/supervisor/immich-microservices-build-seed.log || true
        exit 1
    fi
    sleep 2
done

api_call() {
    local result=""
    for _retry in $(seq 1 60); do
        result=$(curl -sf "$@" 2>/dev/null) || true
        if [ -n "$result" ]; then
            echo "$result"
            return 0
        fi
        sleep 5
    done
    echo "ERROR: API call failed after retries: curl $*" >&2
    return 1
}

psql_retry() {
    for retry in $(seq 1 30); do
        if runuser -u user -- "$PG_BIN/psql" -U user -d immich "$@"; then
            return 0
        fi
        echo "[build-seed] psql failed; retrying ($retry/30)"
        sleep 2
    done
    return 1
}

echo "[build-seed] Creating users"
curl -sf -X POST http://localhost:2283/api/auth/admin-sign-up \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\",\"name\":\"$ADMIN_NAME\"}" >/dev/null || true

ADMIN_LOGIN=$(api_call -X POST http://localhost:2283/api/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}")
ACCESS_TOKEN=$(echo "$ADMIN_LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['accessToken'])")

for user in $AGENT_USERS; do
    agent_number="${user#agent}"
    curl -sf -X POST http://localhost:2283/api/admin/users \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -d "{\"email\":\"${user}@immich.local\",\"password\":\"${user}password\",\"name\":\"Agent ${agent_number}\",\"shouldChangePassword\":false}" >/dev/null || true
    echo "[build-seed] Created ${user}@immich.local"
done

echo "[build-seed] Creating API keys"
API_KEY_RESP=$(api_call -X POST http://localhost:2283/api/api-keys \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d '{"name":"seed-key","permissions":["all"]}')
API_KEY_admin=$(echo "$API_KEY_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['secret'])")

for user in $AGENT_USERS; do
    LOGIN=$(api_call -X POST http://localhost:2283/api/auth/login \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"${user}@immich.local\",\"password\":\"${user}password\"}")
    TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['accessToken'])")
    KEY_RESP=$(api_call -X POST http://localhost:2283/api/api-keys \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d '{"name":"seed-key","permissions":["all"]}')
    KEY=$(echo "$KEY_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['secret'])")
    eval "API_KEY_${user}=\"$KEY\""
done

echo "[build-seed] Uploading photos"
for user in $ALL_USERS; do
    USER_DIR="$PHOTO_DIR/$user"
    if [ ! -d "$USER_DIR" ] || [ -z "$(ls -A "$USER_DIR" 2>/dev/null)" ]; then
        echo "[build-seed] Skipping $user"
        continue
    fi
    eval "USER_KEY=\$API_KEY_${user}"
    count=$(find "$USER_DIR" -type f | wc -l | tr -d ' ')
    echo "[build-seed] Uploading $count files for $user"
    npx --yes @immich/cli@2.5.6 upload \
        --key "$USER_KEY" \
        --url http://localhost:2283/api \
        -r "$USER_DIR/"
done

echo "[build-seed] Waiting for jobs"
sleep 10
for attempt in $(seq 1 160); do
    JOBS=$(curl -sf -H "Authorization: Bearer $ACCESS_TOKEN" http://localhost:2283/api/jobs 2>/dev/null || echo "{}")
    ACTIVE=$(echo "$JOBS" | python3 -c '
import sys, json
try:
    jobs = json.load(sys.stdin)
    print(sum(j.get("jobCounts", {}).get("active", 0) + j.get("jobCounts", {}).get("waiting", 0) for j in jobs.values()))
except Exception:
    print(-1)
' 2>/dev/null || echo "-1")
    if [ "$ACTIVE" = "0" ]; then
        echo "[build-seed] Jobs complete"
        break
    fi
    echo "[build-seed] $ACTIVE jobs remaining"
    sleep 15
done

echo "[build-seed] Finalizing database metadata"
echo "[build-seed] Stopping Immich workers before direct database export"
pkill -TERM -f "/usr/src/app/server/bin/start.sh" 2>/dev/null || true
pkill -TERM -f "python -m immich_ml" 2>/dev/null || true
pkill -TERM -f "redis-server" 2>/dev/null || true
sleep 5
psql_retry -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'immich' AND pid <> pg_backend_pid();"

psql_retry -c \
    "INSERT INTO system_metadata (key, value) VALUES ('admin-onboarding', '{\"isOnboarded\": true}') ON CONFLICT (key) DO UPDATE SET value = '{\"isOnboarded\": true}';"
psql_retry -c \
    "UPDATE \"user\" SET \"shouldChangePassword\" = false;"
psql_retry -c \
    "INSERT INTO user_metadata (\"userId\", key, value) SELECT id, 'preferences', '{\"onboarding\": {\"isOnboarded\": true}}' FROM \"user\" ON CONFLICT (\"userId\", key) DO UPDATE SET value = user_metadata.value || '{\"onboarding\": {\"isOnboarded\": true}}'::jsonb;"

echo "[build-seed] Exporting seed artifacts"
rm -f "$SEED_DIR/immich_db.sql.gz" "$SEED_DIR/upload.tar.gz" "$SEED_DIR/ml-cache.tar.gz"
dumped=0
for retry in $(seq 1 30); do
    if runuser -u user -- "$PG_BIN/pg_dump" -U user --no-owner --no-privileges immich | gzip > "$SEED_DIR/immich_db.sql.gz"; then
        dumped=1
        break
    fi
    echo "[build-seed] pg_dump failed; retrying ($retry/30)"
    sleep 2
done
if [ "$dumped" -ne 1 ]; then
    echo "ERROR: pg_dump failed after retries"
    exit 1
fi
tar czf "$SEED_DIR/upload.tar.gz" -C /data .
tar czf "$SEED_DIR/ml-cache.tar.gz" -C /cache .
chown user:user "$SEED_DIR/immich_db.sql.gz" "$SEED_DIR/upload.tar.gz" "$SEED_DIR/ml-cache.tar.gz"

cleanup
trap - EXIT

echo "[build-seed] Keeping preloaded runtime state for fast container startup"
touch /data/.seeded /cache/.seeded
rm -f "$PG_DATA/postmaster.pid" /var/run/postgresql/.s.PGSQL.5432*
rm -f /tmp/supervisord.pid /var/run/redis/redis-server.pid
find /var/log/supervisor -type f -delete
chown -R user:user "$PG_DATA" /data /cache /var/log/supervisor
echo "[build-seed] Done"
