# syntax=docker/dockerfile:1
# Self-contained Firefly III image: MariaDB data is baked into /var/lib/mysql,
# with no external database service and no persistent Docker volumes.
# Build:  docker build -t firefly-populated .
# Run:    docker run -d --name firefly -p 80:8080 --tmpfs /var/www/html/storage/upload firefly-populated
# Runtime reset: docker exec firefly /usr/local/bin/webarena-reset-state

# ---------------------------------------------------------------------------
# Stage 1: Generate seed SQL. By default the last transaction date is fixed to
# the same date Firefly sees as "today" at runtime.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS seed-sql

ARG FIREFLY_SEED_TODAY=2026-06-24
WORKDIR /seed-builder
COPY generate_seed.py ./
COPY initdb/001-firefly.sql /seed-sql/001-firefly.sql
RUN set -eux; \
    export FIREFLY_SEED_TODAY="${FIREFLY_SEED_TODAY}"; \
    python3 generate_seed.py > /seed-sql/002-seed.sql

# ---------------------------------------------------------------------------
# Stage 2: Pre-populate a MariaDB data directory with seed SQL.
# mariadbd runs briefly at build time, applies the seed files, then shuts
# down. The resulting /seed-data is copied into the final image.
# ---------------------------------------------------------------------------
FROM mariadb:lts AS seeder

COPY --from=seed-sql /seed-sql/ /seed-sql/

RUN set -eux; \
    mkdir -p /seed-data; \
    chown -R mysql:mysql /seed-data; \
    mariadb-install-db --user=mysql --datadir=/seed-data --auth-root-authentication-method=normal; \
    mariadbd --user=mysql --datadir=/seed-data \
        --socket=/tmp/seed.sock --skip-networking & \
    MYSQL_PID=$!; \
    for i in $(seq 1 60); do \
        mariadb-admin --socket=/tmp/seed.sock ping >/dev/null 2>&1 && break; \
        sleep 1; \
    done; \
    mariadb --socket=/tmp/seed.sock -e "\
        CREATE DATABASE firefly CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; \
        CREATE USER 'firefly'@'%' IDENTIFIED BY 'secret_firefly_password'; \
        CREATE USER 'firefly'@'localhost' IDENTIFIED BY 'secret_firefly_password'; \
        GRANT ALL PRIVILEGES ON firefly.* TO 'firefly'@'%'; \
        GRANT ALL PRIVILEGES ON firefly.* TO 'firefly'@'localhost'; \
        FLUSH PRIVILEGES;"; \
    mariadb --socket=/tmp/seed.sock firefly < /seed-sql/001-firefly.sql; \
    mariadb --socket=/tmp/seed.sock firefly < /seed-sql/002-seed.sql; \
    mariadb-admin --socket=/tmp/seed.sock shutdown; \
    wait $MYSQL_PID || true

# ---------------------------------------------------------------------------
# Stage 3: Firefly III runtime with embedded MariaDB.
# ---------------------------------------------------------------------------
FROM fireflyiii/core:latest

LABEL org.opencontainers.image.source="https://github.com/McGill-NLP/webarena-pro"

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends mariadb-server mariadb-client libfaketime && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /var/lib/mysql && \
    mkdir -p /var/lib/mysql /run/mysqld && \
    chown -R mysql:mysql /run/mysqld

COPY --from=seeder --chown=mysql:mysql /seed-data/ /var/lib/mysql/
RUN chown -R mysql:mysql /var/lib/mysql /run/mysqld
RUN mkdir -p /opt/webarena-seed && \
    tar czf /opt/webarena-seed/mysql.tar.gz -C /var/lib mysql

ENV DB_CONNECTION=mysql \
    DB_HOST=127.0.0.1 \
    DB_PORT=3306 \
    DB_DATABASE=firefly \
    DB_USERNAME=firefly \
    DB_PASSWORD=secret_firefly_password \
    APP_ENV=local \
    APP_DEBUG=false \
    APP_KEY=SomeRandomStringOf32CharsExactly \
    STATIC_CRON_TOKEN=12345678901234567890123456789012 \
    TZ=America/Toronto \
    FAKETIME="@2026-06-24 12:00:00" \
    FAKETIME_DONT_FAKE_MONOTONIC=1 \
    TRUSTED_PROXIES="**"

COPY entrypoint.sh /usr/local/bin/firefly-seeded-entrypoint.sh
COPY reset-state.sh /usr/local/bin/webarena-reset-state
RUN chmod +x /usr/local/bin/firefly-seeded-entrypoint.sh /usr/local/bin/webarena-reset-state

# Read-only evaluation API (token-gated; reads the embedded MariaDB directly)
COPY eval_state.php /var/www/html/public/eval_state.php

# Read-only evaluation API (token-gated; reads the embedded MariaDB directly)
COPY eval_state.php /var/www/html/public/eval_state.php

# WebArena-Pro patches over upstream Firefly III: collapse the duplicated
# date controls on the Budgets list and make "Budget > Everything" honor
# the global header date range. Files are overlaid onto the same paths
# they came from in fireflyiii/core:latest.
COPY patches/views/budgets/index.twig /var/www/html/resources/views/budgets/index.twig
COPY patches/views/budgets/show.twig /var/www/html/resources/views/budgets/show.twig
COPY patches/controllers/Budget/ShowController.php /var/www/html/app/Http/Controllers/Budget/ShowController.php
COPY patches/controllers/Chart/BudgetController.php /var/www/html/app/Http/Controllers/Chart/BudgetController.php
COPY patches/routes/breadcrumbs.php /var/www/html/routes/breadcrumbs.php
RUN chown www-data:www-data \
        /var/www/html/resources/views/budgets/index.twig \
        /var/www/html/resources/views/budgets/show.twig \
        /var/www/html/app/Http/Controllers/Budget/ShowController.php \
        /var/www/html/app/Http/Controllers/Chart/BudgetController.php \
        /var/www/html/routes/breadcrumbs.php

# Runs after all /etc/entrypoint.d scripts (including Firefly's own entrypoint,
# which creates cache dirs as root) but before s6 starts php-fpm as www-data.
RUN printf '#!/bin/sh\nchown -R www-data:www-data /var/www/html/storage\n' \
    > /etc/entrypoint.d/99-fix-storage-perms.sh && \
    chmod +x /etc/entrypoint.d/99-fix-storage-perms.sh

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/firefly-seeded-entrypoint.sh"]
CMD ["/init"]
