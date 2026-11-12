#!/usr/bin/env bash
# Generate both CDS layers for Penpot's custom JRE, preserving its seed state.
set -euo pipefail

CONFIG=/tmp/penpot-cache-supervisor.conf
CACHE=/opt/penpot/backend/penpot-cds.jsa
SUPERVISOR_PID=""

cleanup() {
    if [ -n "${SUPERVISOR_PID}" ] && kill -0 "${SUPERVISOR_PID}" 2>/dev/null; then
        supervisorctl -c "${CONFIG}" shutdown >/dev/null 2>&1 || true
        for _ in $(seq 1 240); do
            kill -0 "${SUPERVISOR_PID}" 2>/dev/null || break
            sleep 0.5
        done
        if kill -0 "${SUPERVISOR_PID}" 2>/dev/null; then
            echo "Penpot services did not stop after cache training." >&2
            return 1
        fi
        wait "${SUPERVISOR_PID}" || true
    fi
    SUPERVISOR_PID=""
}
trap cleanup EXIT

tar czf /tmp/penpot-before-cache.tar.gz -C / var/lib/postgresql/15/data opt/data/assets
rm -f "${CACHE}"
# The custom JRE does not ship the base archive required by dynamic CDS.
/opt/jre/bin/java -XX:+UseSerialGC -Xshare:dump
sed '/^\[program:penpot-backend\]/a stopwaitsecs=120' \
    /etc/supervisor/conf.d/supervisord.conf > "${CONFIG}"
JVM_OPTS="-XX:ArchiveClassesAtExit=${CACHE} ${JVM_OPTS:-}" \
    /usr/bin/supervisord -c "${CONFIG}" >/tmp/penpot-cache.log 2>&1 &
SUPERVISOR_PID=$!

ready=0
for _ in $(seq 1 360); do
    if curl -fsS http://127.0.0.1:9001/api/rpc/command/get-profile 2>/dev/null | grep -q '"~:id"'; then
        ready=1
        break
    fi
    kill -0 "${SUPERVISOR_PID}" 2>/dev/null || break
    sleep 0.5
done
if [ "${ready}" != 1 ]; then
    echo "Penpot backend did not become ready while preparing its Java cache." >&2
    exit 1
fi
supervisorctl -c "${CONFIG}" stop penpot-backend
test -s "${CACHE}"
cleanup
trap - EXIT

# Training only prepares classes; it must not publish database/asset mutations.
rm -rf /var/lib/postgresql/15/data /opt/data/assets
tar xzf /tmp/penpot-before-cache.tar.gz -C /
rm -f /tmp/penpot-before-cache.tar.gz "${CONFIG}" /tmp/penpot-cache.log
echo "Penpot Java cache baked; original seed database and assets restored."
