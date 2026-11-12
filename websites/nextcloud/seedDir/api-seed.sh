#!/bin/bash
set -euo pipefail

SEED_ROOT="${NEXTCLOUD_GENERATED_SEED_ROOT:-/generated-seed}"
READY_MARKER="/var/www/html/data/.webarena-seed-v2.ready"
NEXTCLOUD_PUBLIC_URL="${NEXTCLOUD_PUBLIC_URL:-${WP_NEXTCLOUD_URL:-http://localhost}}"
NEXTCLOUD_PUBLIC_URL="${NEXTCLOUD_PUBLIC_URL%/}"
COLLABORA_PUBLIC_URL="${COLLABORA_PUBLIC_URL:-${WP_COLLABORA_URL:-http://localhost:9980}}"
COLLABORA_PUBLIC_URL="${COLLABORA_PUBLIC_URL%/}"

echo "Waiting for Apache port 80 to become available for API seeding..."
until curl -fsS http://127.0.0.1/login > /dev/null 2>&1; do
  sleep 2
done



echo "Apache is up. Executing API seeding scripts..."
bash /seedDir/contacts.sh
bash /seedDir/calendar.sh
bash /seedDir/talk.sh
bash /seedDir/notifications.sh

echo "Verifying bundled Office handshake..."
WP_NEXTCLOUD_URL="${WP_NEXTCLOUD_URL:-$NEXTCLOUD_PUBLIC_URL}" /seedDir/office-ready.sh

echo "Verifying seeded data..."
bash /seedDir/verify.sh

manifest_hash="$(awk '{print $1}' "${SEED_ROOT}/provenance/manifest.sha256")"
printf 'seed_version=2\nmanifest_sha256=%s\n' "$manifest_hash" > "$READY_MARKER"
chown www-data:www-data "$READY_MARKER"

echo "Creating reset snapshot..."
if ! bash /seedDir/create-reset-snapshot.sh; then
  echo "ERROR: failed to create reset snapshot." >&2
  exit 1
fi

echo "API seeding complete. Nextcloud data is ready."
