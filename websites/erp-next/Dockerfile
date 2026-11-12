# Build: docker build -t webarenapro/erp-next .
# Run:   docker run -d --name erp-next -p 8090:8000 webarenapro/erp-next
# Runtime reset: docker exec erp-next /usr/local/bin/webarena-reset-state

FROM frappe/erpnext:v15.56.0

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    mariadb-server \
    redis-server \
    procps \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir requests

RUN mkdir -p /opt/erpnext-seed /home/frappe/custom_scripts \
    && chown -R frappe:frappe /opt/erpnext-seed /home/frappe/custom_scripts

COPY --chown=frappe:frappe seed_data.json /opt/erpnext-seed/seed_data.json
COPY --chown=frappe:frappe scripts/seed_erpnext.py /opt/erpnext-seed/seed_erpnext.py
COPY --chown=frappe:frappe scripts/entrypoint.sh /home/frappe/custom_scripts/entrypoint.sh
COPY --chown=frappe:frappe scripts/healthcheck.sh /home/frappe/custom_scripts/healthcheck.sh
COPY --chown=frappe:frappe scripts/reset-state.sh /home/frappe/custom_scripts/reset-state.sh

RUN chmod +x /home/frappe/custom_scripts/entrypoint.sh \
    /home/frappe/custom_scripts/healthcheck.sh \
    /home/frappe/custom_scripts/reset-state.sh && \
    ln -s /home/frappe/custom_scripts/reset-state.sh /usr/local/bin/webarena-reset-state

ARG WEBARENA_ERPNEXT_PRESEED=1
RUN if [ "$WEBARENA_ERPNEXT_PRESEED" = "1" ]; then \
    WEBARENA_ERPNEXT_SEED_ONLY=1 /home/frappe/custom_scripts/entrypoint.sh; \
    fi

EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=5s --start-period=30s --retries=6 \
    CMD /home/frappe/custom_scripts/healthcheck.sh

ENTRYPOINT ["/home/frappe/custom_scripts/entrypoint.sh"]
