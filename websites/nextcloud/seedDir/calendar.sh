#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

SEED_ROOT="${NEXTCLOUD_GENERATED_SEED_ROOT:-/generated-seed}"
EXPECTED_EVENTS_PER_USER=50
CALENDAR_TIMEZONE="${CALENDAR_TIMEZONE:-America/Toronto}"

curl_retry() {
  curl --retry 8 --retry-delay 1 --retry-max-time 60 --retry-all-errors "$@"
}

set_calendar_timezone() {
  local user="$1"
  local cookie_file="/tmp/${user}-calendar-settings-cookies.txt"
  local html_file="/tmp/${user}-calendar-settings.html"
  local request_token

  curl_retry --fail-with-body --silent --show-error -c "$cookie_file" -u "${user}:agentpass" \
    "http://127.0.0.1/index.php/apps/calendar/" -o "$html_file"
  request_token="$(sed -n 's/.*data-requesttoken="\([^"]*\)".*/\1/p' "$html_file" | head -n 1)"

  if [ -n "$request_token" ]; then
    curl_retry --fail-with-body --silent --show-error -b "$cookie_file" -u "${user}:agentpass" \
      -H "requesttoken: ${request_token}" \
      -X POST "http://127.0.0.1/index.php/apps/calendar/v1/config/timezone" \
      --data-urlencode "value=${CALENDAR_TIMEZONE}" > /dev/null
  else
    echo "WARNING: unable to set calendar timezone for ${user}: request token not found" >&2
  fi
}

remove_default_example_event() {
  local user="$1"
  local calendar_url="http://127.0.0.1/remote.php/dav/calendars/${user}/personal/"
  local response href event_payload

  response="$(curl_retry --fail-with-body --silent --show-error \
    -u "${user}:agentpass" -X PROPFIND -H 'Depth: 1' "$calendar_url")"
  while IFS= read -r href; do
    [ -n "$href" ] || continue
    event_payload="$(curl_retry --fail-with-body --silent --show-error \
      -u "${user}:agentpass" "http://127.0.0.1${href}")"
    if printf '%s\n' "$event_payload" | tr -d '\r' | grep -Fxq 'SUMMARY:Example event - open me!'; then
      echo "Removing Nextcloud's built-in example event for ${user}..."
      curl_retry --fail-with-body --silent --show-error \
        -u "${user}:agentpass" -X DELETE "http://127.0.0.1${href}" > /dev/null
    fi
  done < <(
    printf '%s' "$response" \
      | grep -Eo '<d:href>[^<]+\.ics</d:href>' \
      | sed -e 's#<d:href>##' -e 's#</d:href>##'
  )
}

echo "Seeding Calendar events..."

for user in maya.patel daniel.brooks; do
  remove_default_example_event "$user"
  set_calendar_timezone "$user"
  calendar_dir="${SEED_ROOT}/calendars/${user}"
  imported=0

  while IFS= read -r -d '' event_file; do
    filename="$(basename "$event_file")"
    curl_retry --fail-with-body --silent --show-error \
      -u "${user}:agentpass" \
      -X PUT "http://127.0.0.1/remote.php/dav/calendars/${user}/personal/${filename}" \
      --data-binary "@${event_file}" > /dev/null
    imported=$((imported + 1))
  done < <(find "$calendar_dir" -type f -name '*.ics' -print0 | sort -z)

  if [ "$imported" -ne "$EXPECTED_EVENTS_PER_USER" ]; then
    echo "ERROR: imported ${imported} events for ${user}; expected ${EXPECTED_EVENTS_PER_USER}" >&2
    exit 1
  fi
done

echo "Calendar events seeded."
