# Thunderbird Webmail with task fixtures plus an anonymized Enron-derived corpus.
# Roundcube + Dovecot (IMAP) + fake local SMTP in a single container.
# Data is baked into the image — no external volumes or seed scripts needed.
#
# Build:  docker build -t thunderbird-webarena .
# Run:    docker run -d --name thunderbird -p 8080:80 thunderbird-webarena
# Runtime reset: docker exec thunderbird /usr/local/bin/webarena-reset-state
#
# Webmail UI:  http://localhost:8080
# Primary corpus user: alice@techcorp.local / User@Secure123

FROM ubuntu:22.04

LABEL org.opencontainers.image.source-data="EnronData.org / CMU CALO Enron Email Dataset"
LABEL org.opencontainers.image.source-data-custodian="shackleton-s (anonymized as Alice Chen)"

ENV DEBIAN_FRONTEND=noninteractive

# ── Install system packages ───────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Mail servers
    dovecot-core \
    dovecot-imapd \
    dovecot-sieve \
    dovecot-managesieved \
    postfix \
    # Web stack
    nginx \
    php8.1-fpm \
    php8.1-imap \
    php8.1-intl \
    php8.1-mbstring \
    php8.1-xml \
    php8.1-curl \
    php8.1-zip \
    php8.1-sqlite3 \
    # Process manager
    supervisor \
    # Build-time tools
    python3 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Create vmail user for Dovecot virtual mailboxes ───────────────────────────
RUN groupadd -g 5000 vmail && \
    useradd -u 5000 -g 5000 -d /var/vmail -M -s /usr/sbin/nologin vmail

# ── Download and install Roundcube ───────────────────────────────────────────
ARG ROUNDCUBE_VERSION=1.6.10
RUN curl -fsSL \
    "https://github.com/roundcube/roundcubemail/releases/download/${ROUNDCUBE_VERSION}/roundcubemail-${ROUNDCUBE_VERSION}-complete.tar.gz" \
    -o /tmp/roundcube.tar.gz && \
    mkdir -p /var/www/roundcube && \
    tar -xzf /tmp/roundcube.tar.gz -C /var/www/roundcube --strip-components=1 && \
    rm /tmp/roundcube.tar.gz

# ── Roundcube runtime directories ─────────────────────────────────────────────
RUN mkdir -p \
    /var/lib/roundcube \
    /var/lib/roundcube/temp \
    /var/lib/roundcube/sessions \
    /var/log/roundcube \
    /var/log/supervisor \
    && chown -R www-data:www-data /var/www/roundcube /var/lib/roundcube /var/log/roundcube

# ── Copy configs ──────────────────────────────────────────────────────────────
COPY configs/dovecot.conf         /etc/dovecot/dovecot.conf
COPY configs/postfix-main.cf      /etc/postfix/main.cf
COPY configs/nginx.conf           /etc/nginx/nginx.conf
COPY configs/roundcube.config.php /var/www/roundcube/config/config.inc.php
COPY configs/php-fpm.conf         /etc/php-fpm.conf
COPY configs/supervisord.conf     /etc/supervisor/conf.d/thunderbird.conf
COPY fake_smtp.py                 /usr/local/bin/fake_smtp.py
COPY plugins/webarena_reply/      /var/www/roundcube/plugins/webarena_reply/

# ── Read-only evaluation API (token-gated; reads mailbox state over local IMAP) ─
COPY eval_state.php               /var/www/roundcube/api/eval/state.php
RUN chown -R www-data:www-data /var/www/roundcube/api

# ── Copy PHP-FPM pool config ──────────────────────────────────────────────────
COPY configs/php-fpm.conf /etc/php/8.1/fpm/pool.d/www.conf

# ── Seed: generate Maildir email files at build time ─────────────────────────
COPY seed_data.json       /opt/thunderbird-seed/seed_data.json
COPY seed_assets/         /opt/thunderbird-seed/seed_assets/
COPY generate_maildir.py  /opt/thunderbird-seed/generate_maildir.py
COPY seed_roundcube.py    /opt/thunderbird-seed/seed_roundcube.py
COPY scripts/compile_thread_index.py /opt/thunderbird-seed/compile_thread_index.py

RUN mkdir -p /var/vmail /opt/thunderbird-seed/out && \
    python3 /opt/thunderbird-seed/compile_thread_index.py \
      /opt/thunderbird-seed/seed_assets/messages.jsonl.gz \
      /var/lib/roundcube/thread-index.json.gz && \
    MAILDIR_BASE=/var/vmail \
    SEED_ASSET_DIR=/opt/thunderbird-seed/seed_assets \
    SEED_OUT_DIR=/opt/thunderbird-seed/out \
    python3 /opt/thunderbird-seed/generate_maildir.py && \
    chown www-data:www-data /var/lib/roundcube/thread-index.json.gz

# Initialize Roundcube users, identities, and Alice's complete address book.
RUN SEED_ASSET_DIR=/opt/thunderbird-seed/seed_assets \
    ROUNDCUBE_DB=/var/lib/roundcube/roundcube.db \
    ROUNDCUBE_SCHEMA=/var/www/roundcube/SQL/sqlite.initial.sql \
    python3 /opt/thunderbird-seed/seed_roundcube.py && \
    chown www-data:www-data /var/lib/roundcube/roundcube.db && \
    chmod 660 /var/lib/roundcube/roundcube.db

# ── Apply generated Dovecot passwd and Postfix vmailbox files ─────────────────
RUN cp /opt/thunderbird-seed/out/dovecot-passwd /etc/dovecot/users && \
    chmod 640 /etc/dovecot/users && \
    chown root:dovecot /etc/dovecot/users

RUN cp /opt/thunderbird-seed/out/postfix-vmailbox /etc/postfix/vmailbox && \
    postmap /etc/postfix/vmailbox

# ── Fix ownership ─────────────────────────────────────────────────────────────
RUN chown -R vmail:vmail /var/vmail && \
    chmod -R 700 /var/vmail
RUN mkdir -p /opt/webarena-seed && \
    tar czf /opt/webarena-seed/vmail.tar.gz -C /var vmail

# ── Postfix: set hostname ─────────────────────────────────────────────────────
RUN postconf -e "myhostname=techcorp.local" && \
    echo "techcorp.local" > /etc/mailname

# ── Scripts ───────────────────────────────────────────────────────────────────
COPY scripts/start.sh        /usr/local/bin/start.sh
COPY scripts/healthcheck.sh  /usr/local/bin/healthcheck.sh
COPY scripts/reset-state.sh  /usr/local/bin/webarena-reset-state
RUN chmod +x /usr/local/bin/start.sh /usr/local/bin/healthcheck.sh /usr/local/bin/webarena-reset-state /usr/local/bin/fake_smtp.py

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD /usr/local/bin/healthcheck.sh

ENTRYPOINT ["/usr/local/bin/start.sh"]
