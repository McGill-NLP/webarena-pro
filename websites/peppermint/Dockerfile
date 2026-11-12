# Peppermint with pre-populated mock data (WebArena style)
# Data is baked into the image — no external volumes or pre-steps needed.
#
# Build:  docker build -t peppermint-webarena .
# Run:    docker run -d --name peppermint -p 3000:3000 -p 5003:5003 peppermint-webarena
# Runtime reset: docker exec peppermint /usr/local/bin/webarena-reset-state

# ── Stage 1: Peppermint app sources ───────────────────────────────────────────
# Seed generation produces a portable SQL dump, so run it once on the native
# builder platform. Keep a separate target-platform source for the final image.
FROM --platform=$BUILDPLATFORM pepperlabs/peppermint:latest AS peppermint-seed-src
FROM pepperlabs/peppermint:latest AS peppermint-src

# ── Stage 2: Seeder — boots Postgres + API, seeds, dumps ─────────────────────
FROM --platform=$BUILDPLATFORM node:22-bookworm-slim AS seeder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg lsb-release \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] \
        http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        postgresql-15 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=peppermint-seed-src /apps /apps

ENV PGDATA=/tmp/pgdata

RUN mkdir -p "$PGDATA" /var/run/postgresql \
    && chown -R postgres:postgres "$PGDATA" /var/run/postgresql \
    && runuser -u postgres -- /usr/lib/postgresql/15/bin/initdb \
        -D "$PGDATA" --username=postgres --encoding=UTF8 --locale=C

COPY seed_data.json            /tmp/seed_data.json
COPY data/knowledge_base_documents.json /tmp/knowledge_base_documents.json
COPY data/glpi_tickets.json    /tmp/glpi_tickets.json
COPY data/glpi_knowledge_documents.json /tmp/glpi_knowledge_documents.json
COPY seed/seed_peppermint.js   /tmp/seed_peppermint.js
COPY scripts/build-seed.sh     /tmp/build-seed.sh
RUN chmod +x /tmp/build-seed.sh && /tmp/build-seed.sh

# ── Stage 3: Runtime — single container ──────────────────────────────────────
FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg lsb-release \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] \
        http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        postgresql-15 \
        supervisor \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/webarena-seed

COPY --from=peppermint-src /apps /apps
COPY scripts/patch_peppermint_performance.js /tmp/patch_peppermint_performance.js
COPY scripts/patch-new-ticket-redirect.cjs /tmp/patch-new-ticket-redirect.cjs
RUN node /tmp/patch_peppermint_performance.js /apps \
    && node /tmp/patch-new-ticket-redirect.cjs /apps \
    && rm /tmp/patch_peppermint_performance.js /tmp/patch-new-ticket-redirect.cjs
# PostgreSQL's on-disk format is portable between our 64-bit little-endian
# targets. Copy the database produced by the native seeder so the target
# architecture never has to execute PostgreSQL under emulation during build.
COPY --from=seeder --chown=postgres:postgres /tmp/pgdata/ /var/lib/postgresql/15/data/
COPY --from=seeder /seed.sql.gz /opt/webarena-seed/peppermint_db.sql.gz
COPY data/knowledge_base_documents.json /opt/peppermint-data/knowledge_base_documents.json

ENV PGDATA=/var/lib/postgresql/15/data

RUN mkdir -p "$PGDATA" /var/run/postgresql /var/log/supervisor \
    && chown -R postgres:postgres /var/lib/postgresql /var/run/postgresql \
    && chmod 700 "$PGDATA" \
    && test ! -e "$PGDATA/postmaster.pid"

COPY configs/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY scripts/start.sh         /usr/local/bin/start.sh
COPY scripts/healthcheck.sh   /usr/local/bin/healthcheck.sh
COPY data/glpi_tickets.json   /opt/peppermint-data/glpi_tickets.json
COPY data/glpi_knowledge_documents.json /opt/peppermint-data/glpi_knowledge_documents.json
COPY data/glpi_user_mapping.json /opt/peppermint-data/glpi_user_mapping.json
COPY scripts/reset-state.sh   /usr/local/bin/webarena-reset-state
RUN chmod +x /usr/local/bin/start.sh \
              /usr/local/bin/healthcheck.sh \
              /usr/local/bin/webarena-reset-state

ENV DB_USERNAME=peppermint \
    DB_PASSWORD=peppermint \
    DB_HOST=127.0.0.1 \
    DATABASE_URL="postgresql://peppermint:peppermint@127.0.0.1:5432/peppermint" \
    SECRET=webarena-peppermint-secret-2024 \
    NODE_ENV=production

EXPOSE 3000 5003

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD /usr/local/bin/healthcheck.sh

ENTRYPOINT ["/usr/local/bin/start.sh"]
