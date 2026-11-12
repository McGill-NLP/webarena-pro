#!/bin/bash
# Pin the bundled office server; runtime startup never downloads applications.
set -euo pipefail
version=26.4.502
case "$(dpkg --print-architecture)" in
  amd64) app=richdocumentscode; sha=2879240a8f2b07e629f82d2a322dd23755ff7d9afdefbd470a831e91a15df51c ;;
  arm64) app=richdocumentscode_arm64; sha=c8ec8b906e35d7b4cbf1d4c77d3e840cb2b352a3bd5814810be440c7dc54e28b ;;
  *) echo "Unsupported architecture for bundled Nextcloud Office" >&2; exit 1 ;;
esac
archive="/tmp/${app}.tar.gz"
curl --fail --location --retry 3 --max-time 600 \
  "https://github.com/CollaboraOnline/richdocumentscode/releases/download/${version}/${app}.tar.gz" \
  --output "$archive"
echo "$sha  $archive" | sha256sum --check
mkdir -p /usr/src/nextcloud/custom_apps
tar -xzf "$archive" -C /usr/src/nextcloud/custom_apps
chown -R www-data:www-data "/usr/src/nextcloud/custom_apps/$app"
rm "$archive"
