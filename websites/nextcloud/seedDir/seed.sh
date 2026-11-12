#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

SEED_ROOT="${NEXTCLOUD_GENERATED_SEED_ROOT:-/generated-seed}"
READY_MARKER="/var/www/html/data/.webarena-seed-v2.ready"

until [ -f /var/www/html/config/config.php ]; do
  echo "Waiting for Nextcloud to initialize..."
  sleep 5
done

NEXTCLOUD_HOST_PORT="${WP_NEXTCLOUD_HOST_PORT:-8080}"
case "$NEXTCLOUD_HOST_PORT" in
  ''|*[!0-9]*)
    echo "Invalid WP_NEXTCLOUD_HOST_PORT='${NEXTCLOUD_HOST_PORT}'; falling back to 8080"
    NEXTCLOUD_HOST_PORT="8080"
    ;;
esac

NEXTCLOUD_PUBLIC_SCHEME="${WP_NEXTCLOUD_SCHEME:-${WP_PUBLIC_SCHEME:-http}}"
NEXTCLOUD_PUBLIC_SCHEME="${NEXTCLOUD_PUBLIC_SCHEME%://}"
NEXTCLOUD_PUBLIC_SCHEME="${NEXTCLOUD_PUBLIC_SCHEME%:}"

COLLABORA_HOST_PORT="${WP_COLLABORA_HOST_PORT:-9980}"
case "$COLLABORA_HOST_PORT" in
  ''|*[!0-9]*)
    echo "Invalid WP_COLLABORA_HOST_PORT='${COLLABORA_HOST_PORT}'; falling back to 9980"
    COLLABORA_HOST_PORT="9980"
    ;;
esac

COLLABORA_PUBLIC_HOST="${WP_COLLABORA_HOST:-${WP_NEXTCLOUD_HOST:-${WP_PUBLIC_HOST:-localhost}}}"
COLLABORA_PUBLIC_HOST="${COLLABORA_PUBLIC_HOST%/}"
if [[ "$COLLABORA_PUBLIC_HOST" == *"://"* ]]; then
  COLLABORA_INFERRED_URL="$COLLABORA_PUBLIC_HOST"
elif [[ "$COLLABORA_PUBLIC_HOST" == *":"* ]]; then
  COLLABORA_INFERRED_URL="${NEXTCLOUD_PUBLIC_SCHEME}://${COLLABORA_PUBLIC_HOST}"
else
  COLLABORA_INFERRED_URL="${NEXTCLOUD_PUBLIC_SCHEME}://${COLLABORA_PUBLIC_HOST}:${COLLABORA_HOST_PORT}"
fi
COLLABORA_PUBLIC_URL="${WP_COLLABORA_URL:-${COLLABORA_INFERRED_URL}}"
COLLABORA_PUBLIC_URL="${COLLABORA_PUBLIC_URL%/}"

rm -f "$READY_MARKER"

echo "Configuring Nextcloud applications..."
php occ app:disable password_policy || true
php occ app:disable firstrunwizard || true
php occ config:system:set skeletondirectory --value=""
php occ config:system:set trusted_domains 1 --value="nextcloud"

php occ app:install calendar || true
php occ app:install contacts || true
php occ app:install notes || true
php occ app:install spreed || true
php occ app:install richdocuments
php occ app:enable notifications
if [ -d custom_apps/richdocumentscode_arm64 ]; then
  php occ app:enable richdocumentscode_arm64
else
  php occ app:enable richdocumentscode
fi
php occ config:app:set richdocuments disable_certificate_verification --value="yes"
php occ config:app:set richdocuments wopi_allowlist --value="0.0.0.0/0,127.0.0.1"

export OC_PASS=agentpass
for user in maya.patel daniel.brooks; do
  case "$user" in
    maya.patel)
      display_name="Maya Patel"
      email="maya.patel@cedarstone.test"
      ;;
    daniel.brooks)
      display_name="Daniel Brooks"
      email="daniel.brooks@cedarstone.test"
      ;;
  esac
  if ! php occ user:info "$user" > /dev/null 2>&1; then
    php occ user:add --password-from-env --display-name="$display_name" "$user"
  fi
  php occ user:setting "$user" settings email "$email"

  # Initialize the user's local storage through Nextcloud before copying files.
  # Creating the directory ourselves first makes the initial files:scan report a
  # benign "mkdir(): File exists" error even though every file is indexed.
  SEED_USER="$user" php -r '
    require "/var/www/html/lib/base.php";
    $folder = \OC::$server
      ->get(\OCP\Files\IRootFolder::class)
      ->getUserFolder(getenv("SEED_USER"));
    $placeholder = $folder->newFile(".webarena-seed-init");
    $placeholder->putContent("init");
    $placeholder->delete();
  '
done

echo "Creating supporting Talk participants..."
while IFS=$'\t' read -r user display_name; do
  [ -n "$user" ] || continue
  if ! php occ user:info "$user" > /dev/null 2>&1; then
    php occ user:add --password-from-env --display-name="$display_name" "$user"
  fi
  php occ user:setting "$user" settings email "${user}@cedarstone.test"
done <<'USERS'
sarah	Sarah Chen
priya	Priya Nair
marcus	Marcus Johnson
leon	Leon Greene
USERS

echo "Copying 10,000 populated business files..."
for user in maya.patel daniel.brooks; do
  destination="/var/www/html/data/${user}/files"
  mkdir -p "$destination"
  cp -a "${SEED_ROOT}/files/${user}/." "$destination/"
  chown -R www-data:www-data "/var/www/html/data/${user}"
done

php occ files:scan --all

export COLLABORA_PUBLIC_URL NEXTCLOUD_PUBLIC_SCHEME
if [ "${WEBARENA_NEXTCLOUD_PRESEED_ACTIVE:-0}" = "1" ]; then
  echo "Build-time preseed active; API seeding will run after Apache starts."
else
  echo "Scheduling background API-backed seed import..."
  nohup bash /seedDir/api-seed.sh >/tmp/webarena-nextcloud-api-seed.log 2>&1 &
  echo "$!" > /tmp/webarena-nextcloud-api-seed.pid
fi

echo "Initial file seeding complete."
