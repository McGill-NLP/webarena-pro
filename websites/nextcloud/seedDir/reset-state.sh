#!/bin/bash
set -euo pipefail

SNAPSHOT_DIR="/opt/webarena-seed"
HTML_DIR="/var/www/html"
# Shared URL and filesystem repair for first boot and every snapshot reset.
source /seedDir/runtime-state.sh

snapshot_tree_ready() {
  [ -d "$SNAPSHOT_DIR/tree/config" ] \
    && [ -d "$SNAPSHOT_DIR/tree/data" ] \
    && [ -d "$SNAPSHOT_DIR/tree/custom_apps" ]
}

snapshot_tar_ready() {
  [ -f "$SNAPSHOT_DIR/config.tar.gz" ] \
    && [ -f "$SNAPSHOT_DIR/data.tar.gz" ] \
    && [ -f "$SNAPSHOT_DIR/custom_apps.tar.gz" ]
}

set_maintenance_mode() {
  local enabled

  enabled="$1"
  php -r '
    $configPath = $argv[1];
    $enabled = $argv[2] === "1";
    $CONFIG = [];
    include $configPath;
    $CONFIG["maintenance"] = $enabled;
    file_put_contents(
      $configPath,
      "<?php\n\$CONFIG = " . var_export($CONFIG, true) . ";\n"
    );
  ' "$HTML_DIR/config/config.php" "$enabled" >/dev/null 2>&1 || true
}

for _i in $(seq 1 180); do
  if [ -f "$SNAPSHOT_DIR/ready" ]; then
    break
  fi
  sleep 1
done

if [ ! -e "$SNAPSHOT_DIR/ready" ]; then
  echo "Missing Nextcloud reset snapshot artifact: $SNAPSHOT_DIR/ready" >&2
  exit 1
fi
if ! snapshot_tree_ready && ! snapshot_tar_ready; then
  echo "Missing Nextcloud reset snapshot tree or tarballs in $SNAPSHOT_DIR" >&2
  exit 1
fi

cd "$HTML_DIR"

stop_builtin_office
set_maintenance_mode 1

if snapshot_tree_ready; then
  for directory in config data; do
    if [ -L "$directory" ] || [ ! -d "$directory" ]; then
      rm -rf "$directory"
      mkdir -p "$directory"
    fi
    rsync -a --delete \
      "$SNAPSHOT_DIR/tree/$directory/" \
      "$directory/"
  done
  if [ -L custom_apps ] || [ ! -d custom_apps ]; then
    rm -rf custom_apps
    ln -s "$SNAPSHOT_DIR/tree/custom_apps" custom_apps
    chown -h www-data:www-data custom_apps
  fi
else
  rm -rf config data custom_apps
  tar xzf "$SNAPSHOT_DIR/config.tar.gz" -C /var/www/html
  tar xzf "$SNAPSHOT_DIR/data.tar.gz" -C /var/www/html
  tar xzf "$SNAPSHOT_DIR/custom_apps.tar.gz" -C /var/www/html
  chown -R www-data:www-data config data custom_apps
fi

repair_runtime_state

set_maintenance_mode 0
if ! snapshot_tree_ready; then
  php occ files:scan --all >/dev/null 2>&1 || true
fi

/seedDir/office-ready.sh
echo "[nextcloud-reset] Done."
