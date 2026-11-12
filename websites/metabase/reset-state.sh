#!/bin/bash
set -euo pipefail

PGCTL="/usr/lib/postgresql/14/bin/pg_ctl"
PGDATA="/metabase/pgdata"
RESET_MARK="/tmp/metabase-resetting"
PID_FILE="/tmp/metabase.pid"
SEED_PG="/opt/webarena-seed/pgdata.tar.gz"
SEED_H2="/opt/webarena-seed/metabase-data.tar.gz"

if [ ! -s "$SEED_PG" ] || [ ! -s "$SEED_H2" ]; then
    echo "Missing Metabase seed snapshots under /opt/webarena-seed" >&2
    exit 1
fi

touch "$RESET_MARK"
cleanup() {
    rm -f "$RESET_MARK"
}
trap cleanup EXIT

if [ -s "$PID_FILE" ]; then
    MB_PID="$(cat "$PID_FILE")"
    if kill -0 "$MB_PID" >/dev/null 2>&1; then
        echo "[metabase-reset] Stopping Metabase pid $MB_PID..."
        kill "$MB_PID" >/dev/null 2>&1 || true
        for _i in $(seq 1 60); do
            if ! kill -0 "$MB_PID" >/dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        if kill -0 "$MB_PID" >/dev/null 2>&1; then
            echo "[metabase-reset] Metabase did not stop gracefully; killing pid $MB_PID"
            kill -9 "$MB_PID" >/dev/null 2>&1 || true
            sleep 1
        fi
    fi
fi

echo "[metabase-reset] Stopping PostgreSQL..."
sudo -u postgres "$PGCTL" -D "$PGDATA" stop -m fast >/dev/null 2>&1 || true

echo "[metabase-reset] Restoring PostgreSQL sample data..."
rm -rf "$PGDATA"
tar xzf "$SEED_PG" -C /metabase
chown -R postgres:postgres "$PGDATA"

echo "[metabase-reset] Restoring Metabase H2 data..."
rm -rf /metabase-data
tar xzf "$SEED_H2" -C /
rm -f /metabase.db.mv.db /metabase.db.trace.db /metabase.db.lock.db

echo "[metabase-reset] Starting PostgreSQL..."
sudo -u postgres "$PGCTL" -D "$PGDATA" \
    -o "-c listen_addresses=127.0.0.1 -c shared_buffers=128MB -c max_connections=40 -c fsync=off -c synchronous_commit=off -c full_page_writes=off" \
    -l "$PGDATA/logfile" start

for i in $(seq 1 60); do
    if pg_isready -h localhost -p 5432 -U postgres >/dev/null 2>&1; then
        echo "[metabase-reset] PostgreSQL ready after ${i}s"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "Timed out waiting for PostgreSQL after reset" >&2
        exit 1
    fi
    sleep 1
done

echo "[metabase-reset] Done. Entrypoint will restart Metabase."
