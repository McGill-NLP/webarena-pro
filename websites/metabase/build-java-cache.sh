#!/usr/bin/env bash
# Bake a JVM class archive without changing the image's seeded databases.
set -euo pipefail

PGCTL=/usr/lib/postgresql/14/bin/pg_ctl
PGDATA=/metabase/pgdata
CACHE=/app/metabase-cds.jsa
JAVA_PID=""

cleanup() {
    if [ -n "${JAVA_PID}" ] && kill -0 "${JAVA_PID}" 2>/dev/null; then
        kill -KILL "${JAVA_PID}" 2>/dev/null || true
        wait "${JAVA_PID}" 2>/dev/null || true
    fi
    sudo -u postgres "${PGCTL}" -D "${PGDATA}" stop -m fast >/dev/null 2>&1 || true
}
trap cleanup EXIT

test -s /opt/webarena-seed/pgdata.tar.gz
test -s /opt/webarena-seed/metabase-data.tar.gz
rm -f "${CACHE}"
sudo -u postgres "${PGCTL}" -D "${PGDATA}" -l /tmp/metabase-cache-pg.log start

# Match the runtime JVM options and classpath. This cache belongs to this exact
# JRE/JAR combination and is regenerated whenever the image is rebuilt.
# shellcheck disable=SC2206
java_args=(${METABASE_JAVA_OPTS:-})
java "${java_args[@]}" "-XX:ArchiveClassesAtExit=${CACHE}" \
    -jar /app/metabase.jar >/tmp/metabase-cache.log 2>&1 &
JAVA_PID=$!

ready=0
for _ in $(seq 1 360); do
    if curl -fsS http://127.0.0.1:3000/api/health >/dev/null 2>&1; then
        ready=1
        break
    fi
    kill -0 "${JAVA_PID}" 2>/dev/null || break
    sleep 0.5
done
if [ "${ready}" != 1 ]; then
    echo "Metabase did not become ready while preparing its Java cache." >&2
    exit 1
fi
kill -TERM "${JAVA_PID}"
for _ in $(seq 1 240); do
    kill -0 "${JAVA_PID}" 2>/dev/null || break
    sleep 0.5
done
if kill -0 "${JAVA_PID}" 2>/dev/null; then
    echo "Metabase did not finish writing its Java cache." >&2
    exit 1
fi
wait "${JAVA_PID}" || true
JAVA_PID=""
test -s "${CACHE}"
cleanup
trap - EXIT

# Startup can update both databases. Restore the exact pre-training seed state.
rm -rf "${PGDATA}" /metabase-data
tar xzf /opt/webarena-seed/pgdata.tar.gz -C /metabase
tar xzf /opt/webarena-seed/metabase-data.tar.gz -C /
rm -f /tmp/metabase-cache.log /tmp/metabase-cache-pg.log
echo "Metabase Java cache baked; original seed databases restored."
