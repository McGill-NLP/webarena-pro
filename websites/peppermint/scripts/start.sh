#!/bin/bash
# start.sh — Peppermint single-container entrypoint.
# PostgreSQL is already initialised and seeded at build time.
# Just start all services via supervisord.
mkdir -p /var/log/supervisor
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
