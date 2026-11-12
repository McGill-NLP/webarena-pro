#!/bin/bash
set -euo pipefail

HTML_DIR="/var/www/html"
# Shared URL and filesystem repair for first boot and every snapshot reset.
source /seedDir/runtime-state.sh
SOURCE_DIR="/usr/src/nextcloud"
SNAPSHOT_DIR="/opt/webarena-seed"

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

ensure_custom_apps_snapshot_link() {
  if snapshot_tree_ready && [ ! -L "$HTML_DIR/custom_apps" ]; then
    rm -rf "$HTML_DIR/custom_apps"
    ln -s "$SNAPSHOT_DIR/tree/custom_apps" "$HTML_DIR/custom_apps"
    chown -h www-data:www-data "$HTML_DIR/custom_apps"
  fi
}

restore_preseeded_snapshot() {
  if [ ! -e "$SNAPSHOT_DIR/ready" ]; then
    echo "[nextcloud-preseed] Missing snapshot artifact: $SNAPSHOT_DIR/ready" >&2
    return 1
  fi
  if ! snapshot_tree_ready && ! snapshot_tar_ready; then
    echo "[nextcloud-preseed] Missing Nextcloud reset snapshot tree or tarballs." >&2
    return 1
  fi

  echo "[nextcloud-preseed] Restoring preseeded Nextcloud tree..."
  mkdir -p "$HTML_DIR"
  if [ ! -f "$HTML_DIR/version.php" ]; then
    cp -a "$SOURCE_DIR/." "$HTML_DIR/"
  fi

  if snapshot_tree_ready; then
    for directory in config data; do
      if [ -L "$HTML_DIR/$directory" ] || [ ! -d "$HTML_DIR/$directory" ]; then
        rm -rf "$HTML_DIR/$directory"
        mkdir -p "$HTML_DIR/$directory"
      fi
      rsync -a --delete \
        "$SNAPSHOT_DIR/tree/$directory/" \
        "$HTML_DIR/$directory/"
    done
    ensure_custom_apps_snapshot_link
  else
    rm -rf "$HTML_DIR/config" "$HTML_DIR/data" "$HTML_DIR/custom_apps"
    tar xzf "$SNAPSHOT_DIR/config.tar.gz" -C "$HTML_DIR"
    tar xzf "$SNAPSHOT_DIR/data.tar.gz" -C "$HTML_DIR"
    tar xzf "$SNAPSHOT_DIR/custom_apps.tar.gz" -C "$HTML_DIR"
  fi
  touch "$HTML_DIR/.webarena-preseeded"
}

start_loopback_proxy() {
  local host_port

  host_port="$(php -r '$u=parse_url($argv[1]); echo ($u["scheme"] ?? "http") === "http" ? ($u["port"] ?? 80) : 80;' "$(nextcloud_public_url)")"
  if [ "$host_port" = "80" ]; then
    return 0
  fi
  if command -v socat >/dev/null 2>&1; then
    socat "TCP-LISTEN:${host_port},fork,bind=127.0.0.1,reuseaddr" TCP:127.0.0.1:80 &
  fi
}

if [ -f "$SNAPSHOT_DIR/ready" ]; then
  if [ ! -f "$HTML_DIR/config/config.php" ]; then
    restore_preseeded_snapshot
  fi
  ensure_custom_apps_snapshot_link
  cp /seedDir/office-health.php "$HTML_DIR/webarena-office-health.php"
  rm -f /tmp/webarena-office.ready /tmp/webarena-office.failed
  repair_runtime_state
  start_loopback_proxy
  /seedDir/office-ready.sh &
  exec "$@"
fi

exec /entrypoint.sh "$@"
