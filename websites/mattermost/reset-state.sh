#!/bin/bash
set -euo pipefail

PGDATA="/mm/pgdata"
PGCTL="/usr/lib/postgresql/14/bin/pg_ctl"
SEED_PG="/opt/webarena-seed/pgdata.tar.gz"
SEED_DATA="/opt/webarena-seed/mattermost-data.tar.gz"
PID_FILE=/run/webarena-mattermost.pid
RESET_MARKER=/run/webarena-mattermost-resetting
STOPPED_ACK=/run/webarena-mattermost-stopped

# Serialize resets inside this container as well as in the shared runtime.
exec 9>/run/webarena-mattermost-reset.lock
flock -x 9

if [ ! -s "$SEED_PG" ]; then
    echo "Missing Mattermost PostgreSQL seed snapshot: $SEED_PG" >&2
    exit 1
fi

# Stop the application before its database: Calls owns in-memory sessions and
# RTC listeners which cannot survive a seed restore. PID 1 restarts the child
# only after this script removes the reset marker.
if [ ! -s "$PID_FILE" ]; then
    echo "Mattermost supervisor PID file is missing; reset requires the current image" >&2
    exit 1
fi
mattermost_pid=$(cat "$PID_FILE")
[[ "$mattermost_pid" =~ ^[0-9]+$ ]] || exit 1
rm -f "$STOPPED_ACK"
touch "$RESET_MARKER"
echo "[mattermost-reset] Stopping Mattermost and Calls..."
kill -TERM "$mattermost_pid"
for i in $(seq 1 600); do
    if [ "$(cat "$STOPPED_ACK" 2>/dev/null || true)" = "$mattermost_pid" ]; then break; fi
    if [ "$i" -eq 600 ]; then
        echo "Timed out stopping Mattermost; database has not been restored" >&2
        exit 1
    fi
    sleep 0.1
done

echo "[mattermost-reset] Stopping PostgreSQL..."
sudo -u postgres "$PGCTL" -D "$PGDATA" stop -m fast >/dev/null 2>&1 || true
pg_status=0
sudo -u postgres "$PGCTL" -D "$PGDATA" status >/dev/null 2>&1 || pg_status=$?
if [ "$pg_status" -ne 3 ]; then
    echo "Cannot confirm PostgreSQL is stopped; refusing to restore seed" >&2
    exit 1
fi

echo "[mattermost-reset] Restoring PostgreSQL data..."
rm -rf "$PGDATA"
tar xzf "$SEED_PG" -C /mm
chown -R postgres:postgres "$PGDATA"

echo "[mattermost-reset] Restoring Mattermost file data..."
rm -rf /mm/mattermost-data
mkdir -p /mm/mattermost-data
if [ -s "$SEED_DATA" ]; then
    tar xzf "$SEED_DATA" -C /mm
fi

echo "[mattermost-reset] Starting PostgreSQL..."
sudo -u postgres "$PGCTL" -D "$PGDATA" \
    -o "-c shared_buffers=256MB -c max_connections=300" \
    -l "$PGDATA/logfile" start

for i in $(seq 1 60); do
    if pg_isready -hlocalhost -p 5432 -U mmuser >/dev/null 2>&1; then
        echo "[mattermost-reset] PostgreSQL ready after ${i}s"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "Timed out waiting for PostgreSQL after reset" >&2
        exit 1
    fi
    sleep 1
done

rm -f "$RESET_MARKER"
for i in $(seq 1 120); do
    if curl -fsS http://127.0.0.1:8065/api/v4/system/ping >/dev/null 2>&1 \
        && curl -fsS http://127.0.0.1:8065/plugins/com.mattermost.calls/version >/dev/null 2>&1; then
        echo "[mattermost-reset] Mattermost restarted; Calls state cleared."
        exit 0
    fi
    sleep 1
done
echo "Timed out waiting for Mattermost after reset" >&2
exit 1
