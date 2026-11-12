#!/bin/bash
# Keep PID 1 alive while an in-place reset stops Mattermost and its Calls plugin.
set -euo pipefail

PGCTL=/usr/lib/postgresql/14/bin/pg_ctl
PID_FILE=/run/webarena-mattermost.pid
RESET_MARKER=/run/webarena-mattermost-resetting
STOPPED_ACK=/run/webarena-mattermost-stopped
mattermost_pid=

shutdown() {
    trap - TERM INT
    if [ -n "$mattermost_pid" ]; then
        kill -TERM "$mattermost_pid" 2>/dev/null || true
        wait "$mattermost_pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    sudo -u postgres "$PGCTL" -D /mm/pgdata stop -m fast >/dev/null 2>&1 || true
    exit 0
}
trap shutdown TERM INT

echo "Starting PostgreSQL"
sudo -u postgres "$PGCTL" -D /mm/pgdata \
    -o "-c shared_buffers=256MB -c max_connections=300" \
    -l /mm/pgdata/logfile start

for i in $(seq 1 60); do
    if pg_isready -hlocalhost -p 5432 -U mmuser >/dev/null 2>&1; then
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "Timed out waiting for PostgreSQL" >&2
        exit 1
    fi
    sleep 1
done

# Restrict RTC to the container network interface. Advertising the same NAT
# address for loopback and eth0 produces duplicate ICE candidates.
if [ -n "${MM_CALLS_ICE_HOST_OVERRIDE:-}" ] \
    && { [ -z "${MM_CALLS_UDP_SERVER_ADDRESS+x}" ] || [ -z "${MM_CALLS_TCP_SERVER_ADDRESS+x}" ]; }; then
    calls_bind_ip=$(hostname -I | tr ' ' '\n' | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ && !/^127\./ {print; exit}')
    if [ -z "$calls_bind_ip" ]; then
        echo "Cannot determine Mattermost Calls container IPv4 address" >&2
        exit 1
    fi
    export MM_CALLS_UDP_SERVER_ADDRESS="${MM_CALLS_UDP_SERVER_ADDRESS-$calls_bind_ip}"
    export MM_CALLS_TCP_SERVER_ADDRESS="${MM_CALLS_TCP_SERVER_ADDRESS-$calls_bind_ip}"
fi

cd /mm/mattermost
while true; do
    # A failed/interrupted reset deliberately leaves this marker in place:
    # never start the application against a partially restored database.
    while [ -e "$RESET_MARKER" ]; do sleep 0.1; done
    echo "Starting Mattermost"
    ./bin/mattermost --config=config/config_docker.json &
    mattermost_pid=$!
    echo "$mattermost_pid" > "$PID_FILE"
    status=0
    wait "$mattermost_pid" || status=$?
    stopped_pid=$mattermost_pid
    mattermost_pid=
    rm -f "$PID_FILE"
    if [ ! -e "$RESET_MARKER" ]; then
        exit "$status"
    fi
    # Reset must wait for this acknowledgement before clearing its marker.
    # Otherwise a slow PID 1 could mistake the reset for an unexpected exit.
    echo "$stopped_pid" > "$STOPPED_ACK"
done
