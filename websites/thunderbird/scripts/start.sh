#!/bin/bash
# Container entrypoint.
# Maildir data is already baked in at build time — just start all services.

set -e

# Ensure Roundcube SQLite DB directory is writable by www-data
chown -R www-data:www-data /var/lib/roundcube /var/log/roundcube

mkdir -p /var/log/supervisor

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/thunderbird.conf
