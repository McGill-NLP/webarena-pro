# check=skip=SecretsUsedInArgOrEnv
# Penpot with pre-populated mock data (WebArena style)
# Data is baked into the image — no external volumes or seed scripts needed.
#
# Prerequisites:
#   Run scripts/seed-local.sh first to generate data/penpot_db.sql.gz
#
# Build:  docker build -t penpot-webarena .
# Run:    docker run -d --name penpot -p 9001:9001 penpot-webarena
# Runtime reset: docker exec penpot /usr/local/bin/webarena-reset-state

# ── Stage 1: Penpot image sources (pinned to 2.14.1) ─────────────────────────
FROM penpotapp/frontend:2.14.1  AS penpot-frontend-src
FROM penpotapp/backend:2.14.1   AS penpot-backend-src
FROM penpotapp/exporter:2.14.1  AS penpot-exporter-src

# ── Stage 2: Optional seed data ───────────────────────────────────────────────
FROM alpine:3.19 AS seed-data
COPY data/ /tmp/data/
RUN mkdir -p /tmp/data/assets && \
    if [ -f /tmp/data/penpot_db.sql.gz ]; then \
        cp /tmp/data/penpot_db.sql.gz /seed.sql.gz; \
    else \
        printf '' | gzip -c > /seed.sql.gz; \
        echo "WARNING: data/penpot_db.sql.gz not found — building without seed data."; \
        echo "         Run ./scripts/seed-local.sh first, then rebuild."; \
    fi

# ── Stage 3: Runtime — single container ──────────────────────────────────────
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install PostgreSQL 15, Redis, nginx, supervisord
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg lsb-release \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] \
        http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        postgresql-15 \
        redis-server \
        nginx \
        supervisor \
        fontconfig fonts-liberation fonts-dejavu-core \
        libssl3 libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

# ── Copy JRE from backend image ───────────────────────────────────────────────
# The backend ships its own JRE at /opt/jre — copy it so run.sh can find java
COPY --from=penpot-backend-src /opt/jre /opt/jre
ENV JAVA_HOME=/opt/jre
ENV PATH="/opt/jre/bin:${PATH}"

# ── Copy Node from exporter image ─────────────────────────────────────────────
COPY --from=penpot-exporter-src /opt/node /opt/node
ENV PATH="/opt/node/bin:${PATH}"

# ── Copy Penpot app files ─────────────────────────────────────────────────────
# Frontend: static files served by nginx
COPY --from=penpot-frontend-src /var/www/app           /var/www/app
# Backend: just the backend subdir (contains penpot.jar, run.sh, etc.)
COPY --from=penpot-backend-src  /opt/penpot/backend    /opt/penpot/backend
# Exporter: just the exporter subdir (app.js, node_modules, …)
COPY --from=penpot-exporter-src /opt/penpot/exporter   /opt/penpot/exporter

# The initial pointer position is unset until the cursor enters the canvas.
# Keep Path selection (toolbar and keyboard) safe before that first event.
COPY scripts/patch-path-initialization.cjs /usr/local/bin/patch-path-initialization.cjs
RUN node /usr/local/bin/patch-path-initialization.cjs

# ── Directory structure ───────────────────────────────────────────────────────
RUN mkdir -p \
    /opt/data/assets \
    /opt/webarena-seed \
    /var/lib/postgresql/15/data \
    /var/run/postgresql \
    /var/log/supervisor \
    && chown -R postgres:postgres /var/lib/postgresql /var/run/postgresql

# ── Configs ───────────────────────────────────────────────────────────────────
COPY configs/nginx.conf       /etc/nginx/nginx.conf
COPY configs/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# ── Initialise PostgreSQL and bake in the seeded data (build time) ────────────
COPY --from=seed-data /seed.sql.gz /tmp/seed.sql.gz
COPY --from=seed-data /seed.sql.gz /opt/webarena-seed/penpot_db.sql.gz
COPY --from=seed-data /tmp/data/assets/ /opt/data/assets/
RUN PG_BIN=/usr/lib/postgresql/15/bin && \
    PG_DATA=/var/lib/postgresql/15/data && \
    runuser -u postgres -- $PG_BIN/initdb \
        -D "$PG_DATA" --username=postgres --encoding=UTF8 --locale=C && \
    runuser -u postgres -- $PG_BIN/pg_ctl \
        -D "$PG_DATA" \
        -o "-c listen_addresses=127.0.0.1 -c shared_buffers=128MB -c max_connections=40 -c fsync=off -c synchronous_commit=off -c full_page_writes=off" \
        -l /tmp/pg-build.log start && \
    sleep 3 && \
    runuser -u postgres -- $PG_BIN/psql \
        -c "CREATE USER penpot WITH PASSWORD 'penpot';" && \
    runuser -u postgres -- $PG_BIN/createdb -O penpot penpot && \
    DUMP_SIZE=$(stat -c%s /tmp/seed.sql.gz) && \
    if [ "$DUMP_SIZE" -gt 40 ]; then \
        echo "Restoring seed data ($DUMP_SIZE bytes)..." && \
        gunzip -c /tmp/seed.sql.gz \
            | runuser -u postgres -- $PG_BIN/psql -U penpot -d penpot -q; \
    else \
        echo "No seed data — DB will be empty."; \
    fi && \
    runuser -u postgres -- $PG_BIN/psql -U penpot -d penpot -q -c "UPDATE profile SET props = COALESCE(props, '{}'::jsonb) || jsonb_build_object('~:onboarding-viewed', true, '~:viewed-tutorial?', true, '~:viewed-walkthrough?', true, '~:v2-info-shown', true) WHERE deleted_at IS NULL;" && \
    runuser -u postgres -- $PG_BIN/pg_ctl -D "$PG_DATA" stop -m fast && \
    rm /tmp/seed.sql.gz /tmp/pg-build.log
RUN tar czf /opt/webarena-seed/assets.tar.gz -C /opt/data assets

# ── Scripts ───────────────────────────────────────────────────────────────────
COPY scripts/start.sh            /usr/local/bin/start.sh
COPY scripts/run-backend-fast.sh /usr/local/bin/run-backend-fast.sh
COPY scripts/healthcheck.sh      /usr/local/bin/healthcheck.sh
COPY scripts/reset-state.sh      /usr/local/bin/webarena-reset-state
RUN chmod +x /usr/local/bin/start.sh /usr/local/bin/run-backend-fast.sh \
    /usr/local/bin/healthcheck.sh /usr/local/bin/webarena-reset-state

# ── Environment ───────────────────────────────────────────────────────────────
ENV PENPOT_FLAGS="enable-login-with-password disable-email-verification disable-smtp" \
    PENPOT_DATABASE_URI="postgresql://localhost/penpot" \
    PENPOT_DATABASE_USERNAME="penpot" \
    PENPOT_DATABASE_PASSWORD="penpot" \
    PENPOT_REDIS_URI="redis://localhost:6379/0" \
    PENPOT_ASSETS_STORAGE_BACKEND="assets-fs" \
    PENPOT_STORAGE_ASSETS_FS_DIRECTORY="/opt/data/assets" \
    PENPOT_TELEMETRY_ENABLED="false" \
    PENPOT_SECRET_KEY="webarena-penpot-baked-secret-key-2024" \
    PENPOT_PUBLIC_URI="http://localhost:9001"

EXPOSE 9001

HEALTHCHECK --interval=5s --timeout=5s --start-period=30s --retries=6 \
    CMD /usr/local/bin/healthcheck.sh

ENTRYPOINT ["/usr/local/bin/start.sh"]

# Bake a class cache for this exact JRE and application without changing seed data.
COPY scripts/build-java-cache.sh /usr/local/bin/build-java-cache
RUN bash /usr/local/bin/build-java-cache
