#!/bin/bash
set -euo pipefail

SNAPSHOT_DIR="/opt/webarena-seed"
SNAPSHOT_TREE_DIR="$SNAPSHOT_DIR/tree"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$SNAPSHOT_DIR"

mkdir -p "$TMP_DIR/tree"
cp -a /var/www/html/config "$TMP_DIR/tree/config"
cp -a /var/www/html/data "$TMP_DIR/tree/data"

if [ -d /var/www/html/custom_apps ]; then
  cp -a /var/www/html/custom_apps "$TMP_DIR/tree/custom_apps"
else
  mkdir -p "$TMP_DIR/tree/custom_apps"
fi

rm -rf "$SNAPSHOT_TREE_DIR"
mv "$TMP_DIR/tree" "$SNAPSHOT_TREE_DIR"
rm -f "$SNAPSHOT_DIR/config.tar.gz" \
  "$SNAPSHOT_DIR/data.tar.gz" \
  "$SNAPSHOT_DIR/custom_apps.tar.gz"
touch "$SNAPSHOT_DIR/ready"

echo "Created Nextcloud reset snapshot in $SNAPSHOT_DIR"
