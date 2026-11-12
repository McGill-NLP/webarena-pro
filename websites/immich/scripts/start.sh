#!/bin/bash
set -e

echo "[start.sh] Initializing Immich single-container..."

PG_BIN="/usr/lib/postgresql/14/bin"
PG_DATA="/var/lib/postgresql/14/data"

# ---- Step 1: Initialize PostgreSQL if data dir is empty ----
if [ ! -f "$PG_DATA/PG_VERSION" ]; then
    echo "[start.sh] Initializing PostgreSQL data directory..."
    "$PG_BIN/initdb" -D "$PG_DATA" --username=user --encoding=UTF8 --locale=C

    # Start PG temporarily for restore
    "$PG_BIN/pg_ctl" -D "$PG_DATA" \
        -o "-c config_file=/etc/postgresql/postgresql.conf -c hba_file=/etc/postgresql/pg_hba.conf" \
        -l /var/log/supervisor/pg-init.log start

    # Wait for PG
    echo "[start.sh] Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if "$PG_BIN/pg_isready" -U user -h localhost -q 2>/dev/null; then
            break
        fi
        sleep 1
    done

    # Create database and enable extensions
    "$PG_BIN/createdb" -U user immich 2>/dev/null || true
    "$PG_BIN/psql" -U user -d immich -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null || true
    "$PG_BIN/psql" -U user -d immich -c "CREATE EXTENSION IF NOT EXISTS vchord;" 2>/dev/null || true
    "$PG_BIN/psql" -U user -d immich -c "CREATE EXTENSION IF NOT EXISTS vectors;" 2>/dev/null || true

    # Restore seeded database dump if present
    if [ -f /seed/immich_db.sql.gz ]; then
        echo "[start.sh] Restoring seeded database..."
        gunzip -c /seed/immich_db.sql.gz | "$PG_BIN/psql" -U user -d immich -q
        echo "[start.sh] Database restored."

        # Disable onboarding wizard and password-change prompts
        "$PG_BIN/psql" -U user -d immich -c \
            "INSERT INTO system_metadata (key, value) VALUES ('admin-onboarding', '{\"isOnboarded\": true}') ON CONFLICT (key) DO UPDATE SET value = '{\"isOnboarded\": true}';" 2>/dev/null || true
        "$PG_BIN/psql" -U user -d immich -c \
            "UPDATE \"user\" SET \"shouldChangePassword\" = false;" 2>/dev/null || true
        "$PG_BIN/psql" -U user -d immich -c \
            "INSERT INTO user_metadata (\"userId\", key, value) SELECT id, 'preferences', '{\"onboarding\": {\"isOnboarded\": true}}' FROM \"user\" ON CONFLICT (\"userId\", key) DO UPDATE SET value = user_metadata.value || '{\"onboarding\": {\"isOnboarded\": true}}'::jsonb;" 2>/dev/null || true
        echo "[start.sh] Onboarding & password prompts disabled."
    fi

    # Stop temporary PG — supervisord will manage it from here
    "$PG_BIN/pg_ctl" -D "$PG_DATA" stop -m fast
    echo "[start.sh] PostgreSQL initialized."
fi

# ---- Step 2: Extract seeded uploads if not already done ----
if [ -f /seed/upload.tar.gz ] && [ ! -f /data/.seeded ]; then
    echo "[start.sh] Extracting seeded photos..."
    tar xzf /seed/upload.tar.gz -C /data/
    touch /data/.seeded
    echo "[start.sh] Photos extracted."
fi

# ---- Step 3: Extract ML model cache if not already done ----
if [ -f /seed/ml-cache.tar.gz ] && [ ! -f /cache/.seeded ]; then
    echo "[start.sh] Extracting ML model cache..."
    tar xzf /seed/ml-cache.tar.gz -C /cache/
    touch /cache/.seeded
    echo "[start.sh] ML cache extracted."
fi

# Runtime-only image upgrades reuse the existing seed archives. Prepare them
# during the image build without starting long-lived application services.
if [ "${WEBARENA_IMMICH_PRELOAD_ONLY:-0}" = "1" ]; then
    echo "[start.sh] Seed state preloaded."
    exit 0
fi

# ---- Step 4: Launch all services via supervisord ----
echo "[start.sh] Starting supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
