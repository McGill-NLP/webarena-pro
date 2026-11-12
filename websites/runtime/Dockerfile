# syntax=docker/dockerfile:1
# Apply the current startup/reset contract to an already populated image.
# Build from websites/: docker build -f runtime/Dockerfile --target erp-next \
#   --build-arg BASE_IMAGE=registry/erp-next@sha256:PLATFORM_DIGEST -t webarenapro/erp-next:fast .
# BASE_IMAGE must be the populated image for the selected target.
ARG BASE_IMAGE=scratch

FROM ${BASE_IMAGE} AS erp-next
USER root
COPY erp-next/scripts/entrypoint.sh /home/frappe/custom_scripts/entrypoint.sh
COPY erp-next/scripts/healthcheck.sh /home/frappe/custom_scripts/healthcheck.sh
COPY erp-next/scripts/reset-state.sh /usr/local/bin/webarena-reset-state
RUN chmod +x /home/frappe/custom_scripts/entrypoint.sh \
    /home/frappe/custom_scripts/healthcheck.sh /usr/local/bin/webarena-reset-state \
    && WEBARENA_ERPNEXT_SEED_ONLY=1 /home/frappe/custom_scripts/entrypoint.sh \
    && test -s /opt/erpnext-seed/reset/db.sql.gz \
    && test -f /opt/erpnext-seed/reset/ready
HEALTHCHECK --interval=5s --timeout=5s --start-period=30s --retries=6 \
    CMD /home/frappe/custom_scripts/healthcheck.sh
ENTRYPOINT ["/home/frappe/custom_scripts/entrypoint.sh"]

FROM ${BASE_IMAGE} AS firefly
USER root
COPY firefly/entrypoint.sh /usr/local/bin/firefly-seeded-entrypoint.sh
COPY firefly/reset-state.sh /usr/local/bin/webarena-reset-state
RUN chmod +x /usr/local/bin/firefly-seeded-entrypoint.sh /usr/local/bin/webarena-reset-state \
    && mkdir -p /opt/webarena-seed \
    && tar czf /opt/webarena-seed/mysql.tar.gz -C /var/lib mysql
ENTRYPOINT ["/usr/local/bin/firefly-seeded-entrypoint.sh"]
CMD ["/init"]

FROM ${BASE_IMAGE} AS mattermost
USER root
COPY mattermost/docker-entry-seeded.sh /mm/docker-entry-seeded.sh
COPY mattermost/reset-state.sh /usr/local/bin/webarena-reset-state
RUN chmod +x /mm/docker-entry-seeded.sh /usr/local/bin/webarena-reset-state \
    && mkdir -p /opt/webarena-seed /mm/mattermost-data \
    && tar czf /opt/webarena-seed/pgdata.tar.gz -C /mm pgdata \
    && tar czf /opt/webarena-seed/mattermost-data.tar.gz -C /mm mattermost-data
HEALTHCHECK --interval=5s --timeout=5s --start-period=30s --retries=6 \
    CMD curl -fsS http://127.0.0.1:8065/api/v4/system/ping | grep -q status
ENTRYPOINT ["/mm/docker-entry-seeded.sh"]

FROM ${BASE_IMAGE} AS metabase
USER root
ENV MB_DB_FILE=/metabase-data/metabase.db \
    MB_PLUGINS_DIR=/plugins \
    METABASE_JAVA_OPTS="-XX:+UseSerialGC -XX:TieredStopAtLevel=1 -Djava.awt.headless=true"
COPY metabase/docker-entrypoint.sh /docker-entrypoint.sh
COPY metabase/reset-state.sh /usr/local/bin/webarena-reset-state
RUN chmod +x /docker-entrypoint.sh /usr/local/bin/webarena-reset-state \
    && mkdir -p /metabase-data /plugins /opt/webarena-seed \
    && if [ ! -s /metabase-data/metabase.db.mv.db ] && [ -s /metabase.db.mv.db ]; then \
         cp -a /metabase.db.mv.db /metabase-data/metabase.db.mv.db; \
       fi \
    && test -s /metabase-data/metabase.db.mv.db \
    && tar czf /opt/webarena-seed/pgdata.tar.gz -C /metabase pgdata \
    && tar czf /opt/webarena-seed/metabase-data.tar.gz -C / metabase-data
COPY metabase/build-java-cache.sh /usr/local/bin/build-java-cache
RUN bash /usr/local/bin/build-java-cache
HEALTHCHECK --interval=5s --timeout=5s --start-period=30s --retries=6 \
    CMD curl -fsS http://127.0.0.1:3000/api/health | grep -q status
ENTRYPOINT ["/docker-entrypoint.sh"]

FROM ${BASE_IMAGE} AS immich
USER root
COPY immich/configs/postgresql.conf /etc/postgresql/postgresql.conf
COPY immich/configs/pg_hba.conf /etc/postgresql/pg_hba.conf
COPY immich/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY immich/scripts/start.sh /usr/local/bin/start.sh
COPY immich/scripts/healthcheck.sh /usr/local/bin/healthcheck.sh
COPY immich/scripts/reset-state.sh /usr/local/bin/webarena-reset-state
RUN chmod +x /usr/local/bin/start.sh /usr/local/bin/healthcheck.sh /usr/local/bin/webarena-reset-state
USER user
RUN WEBARENA_IMMICH_PRELOAD_ONLY=1 /usr/local/bin/start.sh \
    && test -f /var/lib/postgresql/14/data/PG_VERSION \
    && test -f /data/.seeded
ENTRYPOINT ["tini", "--"]
CMD ["/usr/local/bin/start.sh"]

FROM ${BASE_IMAGE} AS penpot
USER root
COPY penpot/configs/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY penpot/scripts/start.sh /usr/local/bin/start.sh
COPY penpot/scripts/run-backend-fast.sh /usr/local/bin/run-backend-fast.sh
COPY penpot/scripts/healthcheck.sh /usr/local/bin/healthcheck.sh
COPY penpot/scripts/reset-state.sh /usr/local/bin/webarena-reset-state
RUN chmod +x /usr/local/bin/start.sh /usr/local/bin/run-backend-fast.sh \
    /usr/local/bin/healthcheck.sh /usr/local/bin/webarena-reset-state
RUN mkdir -p /opt/webarena-seed /opt/data/assets \
    && runuser -u postgres -- /usr/lib/postgresql/15/bin/pg_ctl \
         -D /var/lib/postgresql/15/data -l /tmp/pg-snapshot.log start \
    && runuser -u postgres -- /usr/lib/postgresql/15/bin/pg_dump \
         --no-owner --no-privileges -f /tmp/penpot-seed.sql penpot \
    && runuser -u postgres -- /usr/lib/postgresql/15/bin/pg_ctl \
         -D /var/lib/postgresql/15/data stop -m fast \
    && gzip -c /tmp/penpot-seed.sql > /opt/webarena-seed/penpot_db.sql.gz \
    && rm /tmp/penpot-seed.sql \
    && tar czf /opt/webarena-seed/assets.tar.gz -C /opt/data assets
COPY penpot/scripts/build-java-cache.sh /usr/local/bin/build-java-cache
RUN bash /usr/local/bin/build-java-cache
ENTRYPOINT ["/usr/local/bin/start.sh"]

FROM ${BASE_IMAGE} AS password-manager
COPY password-manager/backend/main.py /app/backend/main.py
COPY password-manager/backend/store.py /app/backend/store.py

FROM ${BASE_IMAGE} AS flight-search
COPY flight-search/backend/main.py /app/backend/main.py
COPY flight-search/backend/booking_store.py /app/backend/booking_store.py

FROM ${BASE_IMAGE} AS travelmap
COPY travelmap/app/seed.py /app/app/seed.py
RUN python -c "from app.seed import ensure_database_seeded, create_seed_snapshot; ensure_database_seeded(); create_seed_snapshot()"

FROM ${BASE_IMAGE} AS jobportal
# Preserve this image's initializer and datasets, including image-specific
# catalog imports, before replacing the per-start initialization path.
RUN cp /app/scripts/docker-entrypoint.sh /tmp/original-jobportal-entrypoint.sh
COPY jobportal/core/seed_snapshot.py /app/core/seed_snapshot.py
COPY jobportal/core/urls.py /app/core/urls.py
RUN sh /tmp/original-jobportal-entrypoint.sh python -c "import django; django.setup(); from core.seed_snapshot import create_seed_snapshot; create_seed_snapshot()" \
    && rm /tmp/original-jobportal-entrypoint.sh
COPY jobportal/scripts/docker-entrypoint.sh /app/scripts/docker-entrypoint.sh
RUN chmod +x /app/scripts/docker-entrypoint.sh
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]

FROM ${BASE_IMAGE} AS mydrive
USER root
COPY mydrive/mydrive/start_all.sh /app/start_all.sh
RUN chmod +x /app/start_all.sh && MYDRIVE_PRESEED_ONLY=1 /app/start_all.sh
