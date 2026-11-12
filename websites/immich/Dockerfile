# syntax=docker/dockerfile:1.7
# =============================================================================
# Self-contained Immich image for HF Spaces / WebArena benchmarking
# Bundles: PostgreSQL 14 (pgvector+vchord), Redis, immich-server, immich-ml
# =============================================================================

# --- Stage 1: Immich server artifacts ---
FROM ghcr.io/immich-app/immich-server:release AS immich-server

# --- Stage 2: Immich ML artifacts ---
FROM ghcr.io/immich-app/immich-machine-learning:release AS immich-ml

# --- Stage 3: PostgreSQL with vector extensions ---
FROM ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0 AS immich-db

# =============================================================================
# Stage 4: Runtime — single container with all services
# Using trixie (Debian 13) to match glibc version of immich-server image,
# which is needed for sharp's native bindings.
# =============================================================================
FROM debian:trixie-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive

# Add PostgreSQL APT repo (trixie ships PG17, we need PG14)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] http://apt.postgresql.org/pub/repos/apt trixie-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && rm -rf /var/lib/apt/lists/*

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # PostgreSQL 14
    postgresql-14 \
    postgresql-client-14 \
    # Redis
    redis-server \
    # Process management & utilities
    supervisor \
    tini \
    # Media processing
    ffmpeg \
    libvips42t64 \
    libmimalloc-dev \
    libheif1 \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 24 (matches the version used to build immich-server)
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create user with UID 1000 (HF Spaces requirement)
RUN useradd -m -u 1000 -s /bin/bash user

# ---------------------------------------------------------------------------
# Copy PostgreSQL extensions from immich-db
# ---------------------------------------------------------------------------
COPY --from=immich-db /usr/lib/postgresql/14/lib/vector.so /usr/lib/postgresql/14/lib/
COPY --from=immich-db /usr/lib/postgresql/14/lib/vchord.so /usr/lib/postgresql/14/lib/
COPY --from=immich-db /usr/lib/postgresql/14/lib/vectors.so /usr/lib/postgresql/14/lib/
COPY --from=immich-db /usr/share/postgresql/14/extension/vector* /usr/share/postgresql/14/extension/
COPY --from=immich-db /usr/share/postgresql/14/extension/vchord* /usr/share/postgresql/14/extension/
COPY --from=immich-db /usr/share/postgresql/14/extension/vectors* /usr/share/postgresql/14/extension/

# ---------------------------------------------------------------------------
# Copy Immich server + web frontend + geodata + plugins
# ---------------------------------------------------------------------------
COPY --from=immich-server /usr/src/app /usr/src/app
COPY --from=immich-server /build /build

# ---------------------------------------------------------------------------
# Copy Python 3.11 interpreter from ML image (trixie ships 3.13, but the
# ML venv was built with 3.11)
# ---------------------------------------------------------------------------
COPY --from=immich-ml /usr/local/bin/python3.11 /usr/local/bin/python3.11
COPY --from=immich-ml /usr/local/bin/python3 /usr/local/bin/python3
COPY --from=immich-ml /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=immich-ml /usr/local/lib/libpython3.11.so /usr/local/lib/
COPY --from=immich-ml /usr/local/lib/libpython3.11.so.1.0 /usr/local/lib/
COPY --from=immich-ml /usr/local/lib/libpython3.so /usr/local/lib/
RUN ldconfig

# ---------------------------------------------------------------------------
# Copy Immich ML (Python venv + application code)
# ---------------------------------------------------------------------------
COPY --from=immich-ml /opt/venv /opt/venv
COPY --from=immich-ml /usr/src/immich_ml /usr/src/immich_ml
COPY --from=immich-ml /usr/src/healthcheck.py /usr/src/healthcheck.py

# ---------------------------------------------------------------------------
# Directory structure
# ---------------------------------------------------------------------------
RUN mkdir -p \
    /data/upload /data/library /data/thumbs /data/encoded-video \
    /data/profile /data/backups \
    /var/lib/postgresql/14/data \
    /var/run/postgresql \
    /var/run/redis \
    /cache \
    /seed \
    /var/log/supervisor \
    && chown -R user:user \
        /data /cache /seed \
        /var/log/supervisor \
        /var/lib/postgresql /var/run/postgresql \
        /var/run/redis \
        /usr/src/app /build

# ---------------------------------------------------------------------------
# Copy seed config. Source photos are mounted only for the build-time seeding
# step so the raw photo staging directory is not duplicated in the final image.
# ---------------------------------------------------------------------------
COPY --chown=user seed/.env.seed /seed/.env.seed

# ---------------------------------------------------------------------------
# Copy configs and scripts
# ---------------------------------------------------------------------------
COPY --chown=user configs/postgresql.conf /etc/postgresql/postgresql.conf
COPY --chown=user configs/pg_hba.conf /etc/postgresql/pg_hba.conf
COPY --chown=user supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY --chown=user scripts/start.sh /usr/local/bin/start.sh
COPY --chown=user scripts/healthcheck.sh /usr/local/bin/healthcheck.sh
COPY --chown=user scripts/reset-state.sh /usr/local/bin/webarena-reset-state
COPY scripts/seed-during-build.sh /usr/local/bin/seed-during-build.sh
RUN chmod +x /usr/local/bin/start.sh /usr/local/bin/healthcheck.sh /usr/local/bin/webarena-reset-state /usr/local/bin/seed-during-build.sh

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
ENV NODE_ENV=production \
    IMMICH_HOST=0.0.0.0 \
    IMMICH_MEDIA_LOCATION=/data \
    IMMICH_MACHINE_LEARNING_URL=http://127.0.0.1:3003 \
    DB_HOSTNAME=localhost \
    DB_PORT=5432 \
    DB_USERNAME=user \
    DB_PASSWORD=immich \
    DB_DATABASE_NAME=immich \
    DB_VECTOR_EXTENSION=pgvector \
    PGDATA=/var/lib/postgresql/14/data \
    REDIS_HOSTNAME=127.0.0.1 \
    REDIS_PORT=6379 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/src/app/server/bin:$PATH \
    PYTHONPATH=/usr/src \
    MACHINE_LEARNING_CACHE_FOLDER=/cache \
    MACHINE_LEARNING_WORKERS=1 \
    MACHINE_LEARNING_MODEL_INTER_OP_THREADS=1 \
    MACHINE_LEARNING_MODEL_INTRA_OP_THREADS=1 \
    TRANSFORMERS_CACHE=/cache \
    PYTHONUNBUFFERED=1

RUN --mount=type=bind,source=seed/photos,target=/seed/photos,readonly \
    /usr/local/bin/seed-during-build.sh

USER user
EXPOSE 2283

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD /usr/local/bin/healthcheck.sh

ENTRYPOINT ["tini", "--"]
CMD ["/usr/local/bin/start.sh"]
