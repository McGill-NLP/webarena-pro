#!/bin/bash
set -euo pipefail

SUPERVISOR_CONF="/etc/supervisor/conf.d/supervisord.conf"
PG_BIN="/usr/lib/postgresql/15/bin"
PG_DATA="/var/lib/postgresql/15/data"
SEED_SQL="/opt/webarena-seed/penpot_db.sql.gz"
SEED_ASSETS="/opt/webarena-seed/assets.tar.gz"

if [ ! -s "$SEED_SQL" ]; then
    echo "Missing Penpot database seed: $SEED_SQL" >&2
    exit 1
fi

supervisorctl -c "$SUPERVISOR_CONF" stop nginx penpot-exporter penpot-backend redis postgresql >/dev/null 2>&1 || true

rm -rf "$PG_DATA" /opt/data/assets
mkdir -p "$PG_DATA" /opt/data/assets /var/run/postgresql /var/log/supervisor
chown -R postgres:postgres /var/lib/postgresql /var/run/postgresql

echo "[penpot-reset] Reinitializing PostgreSQL..."
runuser -u postgres -- "$PG_BIN/initdb" -D "$PG_DATA" --username=postgres --encoding=UTF8 --locale=C >/dev/null
runuser -u postgres -- "$PG_BIN/pg_ctl" \
    -D "$PG_DATA" \
    -o "-c listen_addresses=127.0.0.1 -c shared_buffers=128MB -c max_connections=40 -c fsync=off -c synchronous_commit=off -c full_page_writes=off" \
    -l /tmp/pg-reset.log start
sleep 3
runuser -u postgres -- "$PG_BIN/psql" -q -c "CREATE USER penpot WITH PASSWORD 'penpot';"
runuser -u postgres -- "$PG_BIN/createdb" -O penpot penpot
gunzip -c "$SEED_SQL" | runuser -u postgres -- "$PG_BIN/psql" -U penpot -d penpot -q
runuser -u postgres -- "$PG_BIN/pg_ctl" -D "$PG_DATA" stop -m fast

if [ -s "$SEED_ASSETS" ]; then
    tar xzf "$SEED_ASSETS" -C /opt/data
fi

supervisorctl -c "$SUPERVISOR_CONF" start postgresql redis penpot-backend penpot-exporter nginx
echo "[penpot-reset] Done."
