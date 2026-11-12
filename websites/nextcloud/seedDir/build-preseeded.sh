#!/bin/bash
set -euo pipefail

SNAPSHOT_DIR="/opt/webarena-seed"
MAX_WAIT_SECONDS="${WEBARENA_NEXTCLOUD_PRESEED_TIMEOUT:-1800}"
LOG_FILE="/tmp/webarena-nextcloud-preseed.log"
TAIL_PID=""

if [ -f "$SNAPSHOT_DIR/ready" ]; then
  echo "[nextcloud-preseed] Snapshot already exists, skipping build-time seed."
  exit 0
fi

cleanup() {
  if [ -n "${TAIL_PID:-}" ] && kill -0 "$TAIL_PID" 2>/dev/null; then
    kill "$TAIL_PID" 2>/dev/null || true
    wait "$TAIL_PID" 2>/dev/null || true
  fi
  if [ -n "${NEXTCLOUD_PID:-}" ] && kill -0 "$NEXTCLOUD_PID" 2>/dev/null; then
    kill "$NEXTCLOUD_PID" 2>/dev/null || true
    wait "$NEXTCLOUD_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "[nextcloud-preseed] Starting one-time Nextcloud initialization..."
: >"$LOG_FILE"
tail -n +1 -F "$LOG_FILE" >&2 &
TAIL_PID=$!

NEXTCLOUD_TRUSTED_DOMAINS="${NEXTCLOUD_TRUSTED_DOMAINS:-localhost 127.0.0.1}" \
WP_NEXTCLOUD_HOST_PORT="${WP_NEXTCLOUD_HOST_PORT:-80}" \
WP_NEXTCLOUD_URL="${WP_NEXTCLOUD_URL:-http://localhost}" \
WEBARENA_NEXTCLOUD_PRESEED_ACTIVE=1 \
  /entrypoint.sh apache2-foreground >"$LOG_FILE" 2>&1 &
NEXTCLOUD_PID=$!

start_time="$(date +%s)"
deadline=$((start_time + MAX_WAIT_SECONDS))
last_heartbeat="$start_time"
api_seed_started=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  if [ -f "$SNAPSHOT_DIR/ready" ]; then
    echo "[nextcloud-preseed] Snapshot created."
    echo "[nextcloud-preseed] Replacing custom_apps with snapshot symlink."
    rm -rf /var/www/html/custom_apps
    ln -s "$SNAPSHOT_DIR/tree/custom_apps" /var/www/html/custom_apps
    chown -h www-data:www-data /var/www/html/custom_apps
    trap - EXIT
    exit 0
  fi

  if [ "$api_seed_started" = "0" ] && curl -fsS http://127.0.0.1/login >/dev/null 2>&1; then
    echo "[nextcloud-preseed] Apache is ready; running API seed in foreground..."
    if ! WEBARENA_NEXTCLOUD_PRESEED_ACTIVE=1 bash /seedDir/api-seed.sh; then
      echo "[nextcloud-preseed] API seed failed." >&2
      tail -200 "$LOG_FILE" >&2 || true
      exit 1
    fi
    api_seed_started=1
    continue
  fi

  if ! kill -0 "$NEXTCLOUD_PID" 2>/dev/null; then
    echo "[nextcloud-preseed] Nextcloud exited before snapshot was created." >&2
    tail -200 "$LOG_FILE" >&2 || true
    exit 1
  fi

  now="$(date +%s)"
  if [ $((now - last_heartbeat)) -ge 30 ]; then
    echo "[nextcloud-preseed] Still waiting for snapshot after $((now - start_time))s..."
    last_heartbeat="$now"
  fi

  sleep 2
done

echo "[nextcloud-preseed] Timed out after ${MAX_WAIT_SECONDS}s waiting for $SNAPSHOT_DIR/ready." >&2
tail -200 "$LOG_FILE" >&2 || true
exit 1
