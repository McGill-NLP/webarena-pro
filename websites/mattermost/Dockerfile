# syntax=docker/dockerfile:1.7
# Mattermost with pre-populated mock data (WebArena style)
# Data is baked into the image — no external volumes or seed scripts needed.
#
# Build:  docker build -t mattermost-populated .
# Run:    docker run -d --name mattermost -p 8065:8065 mattermost-populated
# Runtime reset: docker exec mattermost /usr/local/bin/webarena-reset-state
#
# Uses Ubuntu base to avoid inherited VOLUME declarations from postgres/mattermost images.
# Mattermost binaries are downloaded from official per-architecture releases so
# the image can be built for both amd64 and arm64. Team Edition keeps the
# complete benchmark history available without an Entry Edition license cap.
#
ARG MATTERMOST_VERSION=11.4.2
ARG MATTERMOST_TEAM_SHA256_AMD64=8dcc384c3fc8c8a88a54f6320cab2bfbfd8067167db256be159ef3d925bb1de0
ARG MATTERMOST_TEAM_SHA256_ARM64=cae35c37b3dfb747e0187ebb9eccb0ea378d4170731dcef4f62b0fb0170cb7aa

FROM --platform=$BUILDPLATFORM ubuntu:22.04 AS mm-source

ARG MATTERMOST_VERSION
ARG MATTERMOST_TEAM_SHA256_AMD64
ARG MATTERMOST_TEAM_SHA256_ARM64
ARG TARGETARCH
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tar \
    && update-ca-certificates >/dev/null 2>&1 \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    mattermost_arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "$mattermost_arch" in \
        amd64) mattermost_sha256="$MATTERMOST_TEAM_SHA256_AMD64" ;; \
        arm64) mattermost_sha256="$MATTERMOST_TEAM_SHA256_ARM64" ;; \
        *) echo "Unsupported Mattermost architecture: $mattermost_arch" >&2; exit 1 ;; \
    esac; \
    mkdir -p /mm; \
    curl -fsSL --retry 3 \
        "https://releases.mattermost.com/${MATTERMOST_VERSION}/mattermost-team-${MATTERMOST_VERSION}-linux-${mattermost_arch}.tar.gz" \
        -o /tmp/mattermost.tar.gz; \
    echo "$mattermost_sha256  /tmp/mattermost.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/mattermost.tar.gz -C /mm; \
    rm /tmp/mattermost.tar.gz; \
    mkdir -p /mm/mattermost-data

# The Team arm64 archive has no prepackaged plugins. Include the same Calls
# version bundled with amd64 so health checks, resets, and task 109 work on both.
ARG MATTERMOST_CALLS_VERSION=1.11.0
ARG MATTERMOST_CALLS_SHA256_ARM64=92beca935d119913af1caf356969f0d1018a3617b108b4b6e19f423e5f536bf0
ARG MATTERMOST_CALLS_SIGNATURE_SHA256_ARM64=37271cdc546cbd755522b46cf10aa87b5db18395ab50b5ac8b2d5d72f0022c48
RUN set -eux; \
    if [ "${TARGETARCH:-$(dpkg --print-architecture)}" = arm64 ]; then \
        plugin="mattermost-plugin-calls-v${MATTERMOST_CALLS_VERSION}-linux-arm64.tar.gz"; \
        plugin_dir=/mm/mattermost/prepackaged_plugins; \
        release_url="https://github.com/mattermost/mattermost-plugin-calls/releases/download/v${MATTERMOST_CALLS_VERSION}"; \
        mkdir -p "$plugin_dir"; \
        curl -fsSL --retry 3 "$release_url/$plugin" -o "$plugin_dir/$plugin"; \
        curl -fsSL --retry 3 "$release_url/$plugin.sig" -o "$plugin_dir/$plugin.sig"; \
        echo "$MATTERMOST_CALLS_SHA256_ARM64  $plugin_dir/$plugin" | sha256sum -c -; \
        echo "$MATTERMOST_CALLS_SIGNATURE_SHA256_ARM64  $plugin_dir/$plugin.sig" | sha256sum -c -; \
    fi

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install PostgreSQL 14 and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-14 \
    ca-certificates \
    curl \
    sudo \
    && update-ca-certificates >/dev/null 2>&1 \
    && rm -rf /var/lib/apt/lists/*

# Copy Mattermost from the release tarball and install Docker config
COPY --from=mm-source /mm /mm
COPY config_docker.json /mm/mattermost/config/config_docker.json

# PostgreSQL configuration
ENV POSTGRES_USER=mmuser
ENV POSTGRES_PASSWORD=mostest
ENV POSTGRES_DB=mattermost_test
ENV PGDATA=/mm/pgdata
ENV MM_SERVICESETTINGS_ENABLETUTORIAL=false
ENV MM_SERVICESETTINGS_ENABLEONBOARDINGFLOW=false
ENV MM_CLOUDSETTINGS_DISABLE=true

# Initialize PostgreSQL with our data directory (not in a VOLUME path)
RUN mkdir -p /mm/pgdata && chown postgres:postgres /mm/pgdata && \
    sudo -u postgres /usr/lib/postgresql/14/bin/initdb -D /mm/pgdata && \
    echo "host all all 0.0.0.0/0 md5" >> /mm/pgdata/pg_hba.conf && \
    echo "local all all trust" >> /mm/pgdata/pg_hba.conf

# Start PostgreSQL, create user/db, load seed data, then stop
COPY mattermost_seed.sql /tmp/mattermost_seed.sql
RUN sudo -u postgres /usr/lib/postgresql/14/bin/pg_ctl -D /mm/pgdata start && \
    sleep 2 && \
    sudo -u postgres psql -c "CREATE USER mmuser WITH PASSWORD 'mostest';" && \
    sudo -u postgres psql -c "CREATE DATABASE mattermost_test OWNER mmuser;" && \
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE mattermost_test TO mmuser;" && \
    sudo -u postgres psql -U mmuser -d mattermost_test -f /tmp/mattermost_seed.sql > /dev/null 2>&1 && \
    sudo -u postgres /usr/lib/postgresql/14/bin/pg_ctl -D /mm/pgdata stop && \
    rm /tmp/mattermost_seed.sql

# Create mattermost data directory
RUN mkdir -p /mm/mattermost-data
RUN mkdir -p /opt/webarena-seed && \
    tar czf /opt/webarena-seed/pgdata.tar.gz -C /mm pgdata && \
    tar czf /opt/webarena-seed/mattermost-data.tar.gz -C /mm mattermost-data

# Copy custom entrypoint
COPY docker-entry-seeded.sh /mm/docker-entry-seeded.sh
COPY reset-state.sh /usr/local/bin/webarena-reset-state
RUN chmod +x /mm/docker-entry-seeded.sh /usr/local/bin/webarena-reset-state

ENV PATH="/mm/mattermost/bin:${PATH}"
WORKDIR /mm
EXPOSE 8065 8443/tcp 8443/udp

HEALTHCHECK --interval=5s --timeout=5s --start-period=30s --retries=6 \
    CMD curl -fsS http://127.0.0.1:8065/api/v4/system/ping | grep -q status \
    && curl -fsS http://127.0.0.1:8065/plugins/com.mattermost.calls/version | grep -q version

ENTRYPOINT ["/mm/docker-entry-seeded.sh"]
