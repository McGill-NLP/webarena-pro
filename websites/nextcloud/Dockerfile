FROM python:3.13-slim AS seed-builder

WORKDIR /seed-build
COPY seed_spec.json ./seed_spec.json
COPY seed ./seed
COPY media ./media

RUN python3 seed/generate.py \
      --spec seed_spec.json \
      --media media \
      --output /generated-seed \
    && python3 -m unittest -v seed/test_generate.py

FROM nextcloud:32.0.12-apache

ENV SQLITE_DATABASE=nextcloud.db
ENV NEXTCLOUD_ADMIN_USER=admin
ENV NEXTCLOUD_ADMIN_PASSWORD=admin

COPY --from=seed-builder /generated-seed /generated-seed
COPY DATASET_CARD.md /usr/share/webarena-nextcloud-seed/DATASET_CARD.md
COPY LICENSES /usr/share/webarena-nextcloud-seed/LICENSES
COPY seedDir /seedDir

RUN chmod +x /seedDir/*.sh \
    && cp /seedDir/seed.sh /docker-entrypoint-hooks.d/post-installation/seed.sh \
    && cp /seedDir/reset-state.sh /usr/local/bin/webarena-reset-state \
    && chmod +x /usr/local/bin/webarena-reset-state

RUN apt-get update \
    && apt-get install -y --no-install-recommends rsync socat libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

RUN php /seedDir/fix-template-picker.php /usr/src/nextcloud/dist/files-init.js

RUN /seedDir/install-office.sh \
    && cp /seedDir/office-health.php /usr/src/nextcloud/webarena-office-health.php

ARG WEBARENA_NEXTCLOUD_PRESEED=1
RUN if [ "$WEBARENA_NEXTCLOUD_PRESEED" = "1" ]; then \
      /seedDir/build-preseeded.sh; \
    fi

# Keep the readiness endpoint outside Nextcloud's front-controller PHP whitelist.
COPY office-health.conf /etc/apache2/conf-enabled/webarena-office-health.conf

FROM scratch

COPY --from=1 / /

ENV APPIMAGE_EXTRACT_AND_RUN=1 \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PHP_INI_DIR=/usr/local/etc/php \
    APACHE_CONFDIR=/etc/apache2 \
    APACHE_ENVVARS=/etc/apache2/envvars \
    PHP_MEMORY_LIMIT=512M \
    PHP_UPLOAD_LIMIT=512M \
    PHP_OPCACHE_MEMORY_CONSUMPTION=128 \
    APACHE_BODY_LIMIT=1073741824 \
    NEXTCLOUD_VERSION=32.0.12 \
    SQLITE_DATABASE=nextcloud.db \
    NEXTCLOUD_ADMIN_USER=admin \
    NEXTCLOUD_ADMIN_PASSWORD=admin

EXPOSE 80
WORKDIR /var/www/html
STOPSIGNAL SIGWINCH

ENTRYPOINT ["/seedDir/docker-entrypoint-preseeded.sh"]
CMD ["apache2-foreground"]

# Probe the routed login page with the configured public Host, since explicit
# trusted_domains may intentionally omit the loopback address.
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=60 \
  CMD test -f /var/www/html/data/.webarena-seed-v2.ready \
    && test -f /tmp/webarena-office.ready \
    && curl --fail --silent --show-error --max-time 2 \
      --header "Host: $(php -r 'include "/var/www/html/config/config.php"; echo parse_url($CONFIG["overwrite.cli.url"], PHP_URL_HOST);')" \
      http://127.0.0.1/login > /dev/null \
    && curl --fail --silent --show-error --max-time 2 \
      --header "Host: $(php -r 'include "/var/www/html/config/config.php"; echo parse_url($CONFIG["overwrite.cli.url"], PHP_URL_HOST);')" \
      http://127.0.0.1/webarena-office-health.php > /dev/null \
    || exit 1
