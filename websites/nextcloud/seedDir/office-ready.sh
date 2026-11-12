#!/bin/bash
set -euo pipefail
HTML_DIR=/var/www/html
source /seedDir/runtime-state.sh
rm -f /tmp/webarena-office.ready /tmp/webarena-office.failed
log=/tmp/webarena-office-startup.log
fail() {
  echo '[nextcloud-office] Office initialization failed; inspect /tmp/webarena-office-startup.log. The image must include the pinned CODE app, and its configured URL must be reachable.' >&2
  touch /tmp/webarena-office.failed
  tail -30 "$log" >&2 || true
}
trap fail ERR
: > "$log"
deadline=$((SECONDS + 180))
until curl -fsS --max-time 5 http://127.0.0.1/login >/dev/null 2>&1; do
  [ "$SECONDS" -lt "$deadline" ]
  sleep 1
done
configure_richdocuments_url "$(nextcloud_public_url)" >>"$log" 2>&1
# The first request may unpack CODE. Retry the native discovery/capability
# handshake, bounded by one startup deadline; do not report login as ready.
activate_office() {
  cd /var/www/html
  local callback=http://localhost
  if [ -n "${WP_COLLABORA_URL:-}" ]; then
    callback="${WP_NEXTCLOUD_CALLBACK_URL:-$(nextcloud_public_url)}"
  fi
  local remaining=$((deadline - SECONDS))
  [ "$remaining" -gt 0 ] || return 1
  if [ "$(id -u)" = 0 ]; then
    timeout --signal=TERM --kill-after=5 "${remaining}s" runuser -u www-data -- php occ richdocuments:activate-config --callback-url="$callback"
  else
    timeout --signal=TERM --kill-after=5 "${remaining}s" php occ richdocuments:activate-config --callback-url="$callback"
  fi
}
until activate_office >>"$log" 2>&1; do
  [ "$SECONDS" -lt "$deadline" ]
  sleep 2
done
# The upstream activation command discovers a public URL. An explicit external
# browser URL takes precedence over its potentially internal discovery origin.
if [ -n "${WP_COLLABORA_URL:-}" ]; then
  configure_richdocuments_url "$(nextcloud_public_url)" >>"$log" 2>&1
  echo external > /tmp/webarena-office.ready
else
  echo bundled > /tmp/webarena-office.ready
fi
echo '[nextcloud-office] Spreadsheet editing is ready.'
