# Metabase with pre-populated sample data — single container, no external services needed.
# Data is baked into the image; PostgreSQL runs inside for the sample DB, Metabase uses H2.
#
# Build:  docker build -t metabase-populated .
# Run:    docker run -d --name metabase -p 3000:3000 metabase-populated
# Runtime reset: docker exec metabase /usr/local/bin/webarena-reset-state
#
FROM metabase/metabase:latest AS mb-source

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    MB_DB_FILE=/metabase-data/metabase.db \
    MB_PLUGINS_DIR=/plugins \
    METABASE_JAVA_OPTS="-XX:+UseSerialGC -XX:TieredStopAtLevel=1 -Djava.awt.headless=true"

# Install Java (for Metabase), PostgreSQL 14 (for sample data), Python3, and utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jre-headless \
    postgresql-14 \
    python3 python3-pip \
    curl sudo ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Metabase jar from official image
COPY --from=mb-source /app/metabase.jar /app/metabase.jar

# PostgreSQL setup — sample data only (Metabase uses its own H2 embedded DB)
ENV PGDATA=/metabase/pgdata
RUN mkdir -p /metabase/pgdata && chown postgres:postgres /metabase/pgdata && \
    sudo -u postgres /usr/lib/postgresql/14/bin/initdb -D /metabase/pgdata && \
    echo "host all all 0.0.0.0/0 md5" >> /metabase/pgdata/pg_hba.conf && \
    echo "local all all trust" >> /metabase/pgdata/pg_hba.conf

# Load sample data into PostgreSQL during build
COPY seed.sql /tmp/seed.sql
RUN sudo -u postgres /usr/lib/postgresql/14/bin/pg_ctl -D /metabase/pgdata start && \
    sleep 2 && \
    sudo -u postgres psql -c "CREATE USER sample WITH PASSWORD 'sample';" && \
    sudo -u postgres psql -c "CREATE DATABASE sample_data OWNER sample;" && \
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE sample_data TO sample;" && \
    sudo -u postgres psql -U sample -d sample_data -f /tmp/seed.sql > /dev/null && \
    sudo -u postgres /usr/lib/postgresql/14/bin/pg_ctl -D /metabase/pgdata stop && \
    rm /tmp/seed.sql

# Metabase H2 data and plugins directories (not VOLUMEs — data is baked in)
RUN mkdir -p /metabase-data /plugins

# Install Python dependencies for setup scripts
COPY requirements.txt /tmp/mb-requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/mb-requirements.txt && rm /tmp/mb-requirements.txt

# Copy setup scripts
COPY setup_scripts/ /app/setup_scripts/

# Copy build-time setup script and run it to bake Metabase state into the image
COPY docker-build-setup.sh /tmp/docker-build-setup.sh
RUN chmod +x /tmp/docker-build-setup.sh && bash /tmp/docker-build-setup.sh && rm /tmp/docker-build-setup.sh
RUN mkdir -p /opt/webarena-seed && \
    tar czf /opt/webarena-seed/pgdata.tar.gz -C /metabase pgdata && \
    tar czf /opt/webarena-seed/metabase-data.tar.gz -C / metabase-data

# Copy runtime entrypoint
COPY docker-entrypoint.sh /docker-entrypoint.sh
COPY reset-state.sh /usr/local/bin/webarena-reset-state
RUN chmod +x /docker-entrypoint.sh /usr/local/bin/webarena-reset-state

COPY build-java-cache.sh /usr/local/bin/build-java-cache
RUN bash /usr/local/bin/build-java-cache

EXPOSE 3000
HEALTHCHECK --interval=5s --timeout=5s --start-period=30s --retries=6 \
    CMD curl -fsS http://127.0.0.1:3000/api/health | grep -q status

ENTRYPOINT ["/docker-entrypoint.sh"]
