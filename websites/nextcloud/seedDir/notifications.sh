#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

SEED_ROOT="${NEXTCLOUD_GENERATED_SEED_ROOT:-/generated-seed}"
NOTIFICATIONS_FILE="${SEED_ROOT}/notifications/notifications.tsv"
EXPECTED_PER_USER=12

echo "Creating deterministic business notifications..."
for user in maya.patel daniel.brooks; do
  user_count="$(awk -F '\t' -v user="$user" '$1 == user {count++} END {print count + 0}' "$NOTIFICATIONS_FILE")"
  if [ "$user_count" -ne "$EXPECTED_PER_USER" ]; then
    echo "ERROR: notification seed contains ${user_count} rows for ${user}; expected ${EXPECTED_PER_USER}" >&2
    exit 1
  fi
done

while IFS=$'\t' read -r user object_id subject message; do
  [ -n "$user" ] || continue
  php occ notification:generate \
    --no-interaction \
    --object-type="webarena_seed" \
    --object-id="$object_id" \
    --long-message="$message" \
    "$user" "$subject" > /dev/null
done < "$NOTIFICATIONS_FILE"

echo "Business notifications seeded."
