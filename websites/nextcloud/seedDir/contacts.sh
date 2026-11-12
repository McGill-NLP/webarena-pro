#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

SEED_ROOT="${NEXTCLOUD_GENERATED_SEED_ROOT:-/generated-seed}"
EXPECTED_CONTACTS_PER_USER=100

curl_retry() {
  curl --retry 8 --retry-delay 1 --retry-max-time 60 --retry-all-errors "$@"
}

echo "Seeding Contacts..."

remove_default_example_contact() {
  local user="$1"
  local default_url="http://127.0.0.1/remote.php/dav/addressbooks/users/${user}/contacts/default"
  local payload

  if payload="$(curl_retry --fail-with-body --silent --show-error -u "${user}:agentpass" "$default_url" 2>/dev/null)"; then
    if grep -q 'FN:Leon Green' <<< "$payload" \
      && grep -q 'ADR;TYPE=HOME:;;123 Street Street;City;State;;Country' <<< "$payload" \
      && grep -q 'TEL;TYPE=HOME,VOICE:+999999999999' <<< "$payload"; then
      echo "Removing Nextcloud's built-in example contact for ${user}..."
      curl_retry --fail-with-body --silent --show-error \
        -u "${user}:agentpass" -X DELETE "$default_url" > /dev/null
    fi
  fi
}

for user in maya.patel daniel.brooks; do
  remove_default_example_contact "$user"
  contact_dir="${SEED_ROOT}/contacts/${user}"
  imported=0

  while IFS= read -r -d '' vcard; do
    filename="$(basename "$vcard")"
    curl_retry --fail-with-body --silent --show-error \
      -u "${user}:agentpass" \
      -X PUT "http://127.0.0.1/remote.php/dav/addressbooks/users/${user}/contacts/${filename}" \
      --data-binary "@${vcard}" > /dev/null
    imported=$((imported + 1))
  done < <(find "$contact_dir" -type f -name '*.vcf' -print0 | sort -z)

  if [ "$imported" -ne "$EXPECTED_CONTACTS_PER_USER" ]; then
    echo "ERROR: imported ${imported} contacts for ${user}; expected ${EXPECTED_CONTACTS_PER_USER}" >&2
    exit 1
  fi
done

echo "Contacts seeded."
