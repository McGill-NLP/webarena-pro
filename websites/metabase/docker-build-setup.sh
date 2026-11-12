#!/bin/bash
# Runs during docker build to bake Metabase state into the image.
# Starts PostgreSQL (sample data) + Metabase (H2), runs setup, then stops both.
set -e

PGCTL=/usr/lib/postgresql/14/bin/pg_ctl
PGDATA=/metabase/pgdata
MB_PID=

java_args=()
if [ -n "${METABASE_JAVA_OPTS:-}" ]; then
    # Intentionally split JVM options supplied by the Dockerfile/env.
    # shellcheck disable=SC2206
    java_args=(${METABASE_JAVA_OPTS})
fi

cleanup() {
    if [ -n "$MB_PID" ] && kill -0 "$MB_PID" >/dev/null 2>&1; then
        kill "$MB_PID" >/dev/null 2>&1 || true
        wait "$MB_PID" 2>/dev/null || true
    fi
    sudo -u postgres $PGCTL -D $PGDATA stop >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== Starting PostgreSQL ==="
sudo -u postgres $PGCTL -D $PGDATA \
    -o "-c listen_addresses=127.0.0.1 -c shared_buffers=128MB -c max_connections=40 -c fsync=off -c synchronous_commit=off -c full_page_writes=off" \
    start
until pg_isready -h localhost -p 5432 -U postgres > /dev/null 2>&1; do
    echo "  Waiting for PostgreSQL..."
    sleep 1
done
echo "  PostgreSQL is ready"

echo "=== Starting Metabase (H2 mode) ==="
java "${java_args[@]}" -jar /app/metabase.jar &
MB_PID=$!

echo "  Waiting for Metabase to become ready (this takes a few minutes)..."
timeout=300
while [ $timeout -gt 0 ]; do
    if curl -sf http://localhost:3000/api/health > /dev/null 2>&1; then
        echo "  Metabase is ready"
        break
    fi
    sleep 2
    timeout=$((timeout - 2))
done

if [ $timeout -le 0 ]; then
    echo "ERROR: Metabase did not start in time"
    exit 1
fi

echo "=== Running setup scripts ==="
MY_DB_HOST=localhost python3 /app/setup_scripts/setup_all.py

echo "=== Stopping Metabase ==="
kill $MB_PID 2>/dev/null || true
wait $MB_PID 2>/dev/null || true
MB_PID=

echo "=== Stopping PostgreSQL ==="
sudo -u postgres $PGCTL -D $PGDATA stop
trap - EXIT

echo "=== Build-time setup complete ==="
