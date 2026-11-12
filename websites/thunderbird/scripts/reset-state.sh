#!/bin/bash
set -euo pipefail

SUPERVISOR_CONF="/etc/supervisor/conf.d/thunderbird.conf"
SEED_VMAIL="/opt/webarena-seed/vmail.tar.gz"

if [ ! -s "$SEED_VMAIL" ]; then
    echo "Missing Thunderbird mail seed: $SEED_VMAIL" >&2
    exit 1
fi

supervisorctl -c "$SUPERVISOR_CONF" stop nginx php-fpm dovecot fake-smtp >/dev/null 2>&1 || true

rm -rf /var/vmail
tar xzf "$SEED_VMAIL" -C /var
chown -R vmail:vmail /var/vmail
chmod -R 700 /var/vmail

rm -f /var/lib/roundcube/roundcube.db
rm -rf /var/lib/roundcube/temp /var/lib/roundcube/sessions
mkdir -p /var/lib/roundcube/temp /var/lib/roundcube/sessions
chown -R www-data:www-data /var/lib/roundcube /var/log/roundcube

supervisorctl -c "$SUPERVISOR_CONF" start fake-smtp dovecot php-fpm nginx
echo "[thunderbird-reset] Done."
