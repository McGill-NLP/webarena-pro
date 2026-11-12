#!/bin/bash
set -euo pipefail

SUPERVISOR_CONF="/etc/supervisor/conf.d/supervisord.conf"
PG_BIN="/usr/lib/postgresql/14/bin"
PG_DATA="/var/lib/postgresql/14/data"
SEED_DIR="/seed"

if [ ! -s "$SEED_DIR/immich_db.sql.gz" ]; then
    echo "Missing Immich database seed: $SEED_DIR/immich_db.sql.gz" >&2
    exit 1
fi

supervisorctl -c "$SUPERVISOR_CONF" stop immich-api immich-microservices immich-ml redis postgresql >/dev/null 2>&1 || true
"$PG_BIN/pg_ctl" -D "$PG_DATA" stop -m fast >/dev/null 2>&1 || true

for i in $(seq 1 30); do
    if ! "$PG_BIN/pg_ctl" -D "$PG_DATA" status >/dev/null 2>&1; then
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "Timed out waiting for PostgreSQL to stop during Immich reset" >&2
        exit 1
    fi
    sleep 1
done

find "$PG_DATA" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} +
find /cache -mindepth 1 -maxdepth 1 -exec rm -rf {} +
mkdir -p "$PG_DATA" /data /cache /var/run/postgresql /var/run/redis /var/log/supervisor
rm -f "$PG_DATA/postmaster.pid" /var/run/postgresql/.s.PGSQL.5432*

echo "[immich-reset] Reinitializing PostgreSQL..."
"$PG_BIN/initdb" -D "$PG_DATA" --username=user --encoding=UTF8 --locale=C >/dev/null
"$PG_BIN/pg_ctl" -D "$PG_DATA" \
    -o "-c config_file=/etc/postgresql/postgresql.conf -c hba_file=/etc/postgresql/pg_hba.conf" \
    -l /var/log/supervisor/pg-reset.log start

for i in $(seq 1 60); do
    if "$PG_BIN/pg_isready" -U user -h localhost -q >/dev/null 2>&1; then
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "Timed out waiting for PostgreSQL during Immich reset" >&2
        exit 1
    fi
    sleep 1
done

"$PG_BIN/createdb" -U user immich
"$PG_BIN/psql" -U user -d immich -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
"$PG_BIN/psql" -U user -d immich -c "CREATE EXTENSION IF NOT EXISTS vchord;" >/dev/null
"$PG_BIN/psql" -U user -d immich -c "CREATE EXTENSION IF NOT EXISTS vectors;" >/dev/null
gunzip -c "$SEED_DIR/immich_db.sql.gz" | "$PG_BIN/psql" -U user -d immich -q
"$PG_BIN/pg_ctl" -D "$PG_DATA" stop -m fast

if [ -s "$SEED_DIR/upload.tar.gz" ]; then
    tar xzf "$SEED_DIR/upload.tar.gz" -C /data/
    touch /data/.seeded
fi
if [ -s "$SEED_DIR/ml-cache.tar.gz" ]; then
    tar xzf "$SEED_DIR/ml-cache.tar.gz" -C /cache/
    touch /cache/.seeded
fi

echo "[immich-reset] Restarting services..."
supervisorctl -c "$SUPERVISOR_CONF" start postgresql redis immich-ml immich-microservices immich-api
echo "[immich-reset] Done."
