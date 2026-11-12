#!/bin/bash
# Entrypoint: starts PostgreSQL (sample data) then Metabase, then saves a fresh auth state.
set -euo pipefail

PGCTL=/usr/lib/postgresql/14/bin/pg_ctl
PGDATA=/metabase/pgdata

export MB_DB_FILE="${MB_DB_FILE:-/metabase-data/metabase.db}"
export MB_PLUGINS_DIR="${MB_PLUGINS_DIR:-/plugins}"

java_args=()
if [ -n "${METABASE_JAVA_OPTS:-}" ]; then
    # Intentionally split JVM options supplied by the Dockerfile/env.
    # shellcheck disable=SC2206
    java_args=(${METABASE_JAVA_OPTS})
fi

if [ -s /app/metabase-cds.jsa ]; then
    java_args+=("-XX:SharedArchiveFile=/app/metabase-cds.jsa")
fi

echo "Starting PostgreSQL"
sudo -u postgres $PGCTL -D $PGDATA \
    -o "-c listen_addresses=127.0.0.1 -c shared_buffers=128MB -c max_connections=40 -c fsync=off -c synchronous_commit=off -c full_page_writes=off" \
    -l $PGDATA/logfile start

until pg_isready -h localhost -p 5432 -U postgres > /dev/null 2>&1; do
    echo "  PostgreSQL still starting..."
    sleep 0.5
done
echo "PostgreSQL is ready"

rm -f "${MB_DB_FILE}.lock.db" /metabase.db.lock.db

while true; do
    echo "Starting Metabase"
    java "${java_args[@]}" -jar /app/metabase.jar &
    MB_PID=$!
    echo "$MB_PID" > /tmp/metabase.pid

    echo "Waiting for Metabase to become ready..."
    timeout=180
    while [ $timeout -gt 0 ]; do
        if curl -sf http://localhost:3000/api/health > /dev/null 2>&1; then
            echo "Metabase is ready"
            break
        fi
        if ! kill -0 "$MB_PID" >/dev/null 2>&1; then
            break
        fi
        sleep 1
        timeout=$((timeout - 1))
    done

    if [ $timeout -gt 0 ] && kill -0 "$MB_PID" >/dev/null 2>&1; then
        echo "Saving fresh auth state..."
        AUTH_STATE_PATH=/metabase/.auth/metabase_admin_state.json \
        METABASE_URL=http://localhost:3000 \
            python3 /app/setup_scripts/save_auth_state.py || echo "Warning: could not save auth state"
    fi

    status=0
    wait "$MB_PID" || status=$?
    rm -f /tmp/metabase.pid

    if [ -f /tmp/metabase-resetting ]; then
        echo "Metabase reset in progress; waiting to restart..."
        while [ -f /tmp/metabase-resetting ]; do
            sleep 1
        done
        continue
    fi

    exit "$status"
done
