#!/bin/bash
set -euo pipefail

SUPERVISOR_CONF="/etc/supervisor/conf.d/supervisord.conf"
PG_BIN="/usr/lib/postgresql/15/bin"
PG_DATA="/var/lib/postgresql/15/data"
SEED_SQL="/opt/webarena-seed/peppermint_db.sql.gz"

if [ ! -s "$SEED_SQL" ]; then
    echo "Missing Peppermint database seed: $SEED_SQL" >&2
    exit 1
fi

supervisorctl -c "$SUPERVISOR_CONF" stop peppermint-client peppermint-api postgresql >/dev/null 2>&1 || true

rm -rf "$PG_DATA"
mkdir -p "$PG_DATA" /var/run/postgresql /var/log/supervisor
chown -R postgres:postgres /var/lib/postgresql /var/run/postgresql

echo "[peppermint-reset] Reinitializing PostgreSQL..."
runuser -u postgres -- "$PG_BIN/initdb" -D "$PG_DATA" --username=postgres --encoding=UTF8 --locale=C >/dev/null
runuser -u postgres -- "$PG_BIN/pg_ctl" \
    -D "$PG_DATA" -o "-c listen_addresses=127.0.0.1" \
    -l /tmp/pg-reset.log start
sleep 3
runuser -u postgres -- psql -q -c "CREATE USER peppermint WITH PASSWORD 'peppermint';"
runuser -u postgres -- psql -q -c "CREATE DATABASE peppermint OWNER peppermint;"
runuser -u postgres -- psql -q -c "GRANT ALL PRIVILEGES ON DATABASE peppermint TO peppermint;"
gunzip -c "$SEED_SQL" | runuser -u postgres -- psql -U peppermint -d peppermint -q
runuser -u postgres -- "$PG_BIN/pg_ctl" -D "$PG_DATA" stop -m fast

supervisorctl -c "$SUPERVISOR_CONF" start postgresql peppermint-api peppermint-client
echo "[peppermint-reset] Done."
