#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

SEED_ROOT="${NEXTCLOUD_GENERATED_SEED_ROOT:-/generated-seed}"
MESSAGES_FILE="${SEED_ROOT}/talk/messages.tsv"
ROOMS_FILE="${SEED_ROOT}/talk/rooms.tsv"
UNREAD_FILE="${SEED_ROOT}/talk/unread.tsv"
TOKEN_FILE="/var/www/html/data/.webarena-talk-tokens.tsv"
MESSAGE_ID_FILE="/var/www/html/data/.webarena-talk-message-ids.tsv"
EXPECTED_MESSAGES=425

message_count="$(wc -l < "$MESSAGES_FILE" | tr -d ' ')"
if [ "$message_count" -ne "$EXPECTED_MESSAGES" ]; then
  echo "ERROR: Talk seed contains ${message_count} messages; expected ${EXPECTED_MESSAGES}" >&2
  exit 1
fi

: > "$TOKEN_FILE"
: > "$MESSAGE_ID_FILE"
declare -A message_ids
echo "Creating multi-user Talk rooms and seeding threaded messages..."

while IFS=$'\t' read -r room participants_csv; do
  [ -n "$room" ] || continue
  room_output="$(php occ talk:room:create --user maya.patel --public "$room")"
  token="$(printf '%s\n' "$room_output" | awk '/Room token:/ {print $3; exit}')"
  if [ -z "$token" ]; then
    echo "ERROR: unable to determine token for Talk room '${room}'" >&2
    printf '%s\n' "$room_output" >&2
    exit 1
  fi

  IFS=',' read -r -a participants <<< "$participants_csv"
  for participant in "${participants[@]}"; do
    [ "$participant" = "maya.patel" ] && continue
    php occ talk:room:add --user "$participant" "$token" > /dev/null
  done
  printf '%s\t%s\n' "$room" "$token" >> "$TOKEN_FILE"

  while IFS=$'\t' read -r row_room author message_key reply_to_key thread_title message; do
    [ "$row_room" = "$room" ] || continue
    reply_to_id=0
    if [ "$reply_to_key" != "-" ]; then
      reply_to_id="${message_ids[$reply_to_key]:-}"
      if [ -z "$reply_to_id" ]; then
        echo "ERROR: Talk reply ${message_key} references unknown message ${reply_to_key}" >&2
        exit 1
      fi
    fi
    [ "$thread_title" = "-" ] && thread_title=""

    payload="$(php -r '
      echo json_encode([
        "message" => $argv[1],
        "replyTo" => (int)$argv[2],
        "threadTitle" => $argv[3],
        "referenceId" => "webarena-seed-v2-" . $argv[4],
      ], JSON_UNESCAPED_SLASHES);
    ' "$message" "$reply_to_id" "$thread_title" "$message_key")"
    response="$(curl --fail-with-body --silent --show-error \
      -u "${author}:agentpass" \
      -X POST "http://127.0.0.1/ocs/v2.php/apps/spreed/api/v1/chat/${token}" \
      -H "OCS-APIRequest: true" \
      -H "Accept: application/json" \
      -H "Content-Type: application/json" \
      -d "$payload")"
    server_id="$(printf '%s' "$response" | php -r '
      $payload = json_decode(stream_get_contents(STDIN), true);
      echo $payload["ocs"]["data"]["id"] ?? "";
    ')"
    if [ -z "$server_id" ]; then
      echo "ERROR: Talk did not return an ID for message ${message_key}" >&2
      printf '%s\n' "$response" >&2
      exit 1
    fi
    message_ids["$message_key"]="$server_id"
    printf '%s\t%s\t%s\t%s\n' "$room" "$message_key" "$author" "$server_id" >> "$MESSAGE_ID_FILE"
  done < "$MESSAGES_FILE"

  # Establish a clean read baseline for every room member before applying the
  # deterministic per-agent unread states below.
  for participant in "${participants[@]}"; do
    curl --fail-with-body --silent --show-error \
      -u "${participant}:agentpass" \
      -X POST "http://127.0.0.1/ocs/v2.php/apps/spreed/api/v1/chat/${token}/read" \
      -H "OCS-APIRequest: true" \
      -H "Accept: application/json" \
      -H "Content-Type: application/json" \
      -d '{}' > /dev/null
  done
done < "$ROOMS_FILE"

echo "Applying deterministic unread conversation markers..."
while IFS=$'\t' read -r user room unread_count; do
  [ -n "$user" ] || continue
  token="$(awk -F '\t' -v room="$room" '$1 == room {print $2; exit}' "$TOKEN_FILE")"
  room_message_count="$(awk -F '\t' -v room="$room" '$1 == room {count++} END {print count + 0}' "$MESSAGE_ID_FILE")"
  read_index=$((room_message_count - unread_count))
  if [ "$read_index" -lt 1 ]; then
    marker=-1
  else
    marker="$(awk -F '\t' -v room="$room" -v target="$read_index" '
      $1 == room {count++; if (count == target) {print $4; exit}}
    ' "$MESSAGE_ID_FILE")"
  fi
  if [ -z "$token" ] || [ -z "$marker" ]; then
    echo "ERROR: unable to set unread marker for ${user} in ${room}" >&2
    exit 1
  fi
  payload="$(php -r 'echo json_encode(["lastReadMessage" => (int)$argv[1]]);' "$marker")"
  curl --fail-with-body --silent --show-error \
    -u "${user}:agentpass" \
    -X POST "http://127.0.0.1/ocs/v2.php/apps/spreed/api/v1/chat/${token}/read" \
    -H "OCS-APIRequest: true" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    -d "$payload" > /dev/null
done < "$UNREAD_FILE"

chown www-data:www-data "$TOKEN_FILE" "$MESSAGE_ID_FILE"
echo "Talk messages, participants, threads, and unread states seeded."
