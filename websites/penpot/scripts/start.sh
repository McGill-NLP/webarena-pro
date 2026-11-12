#!/bin/bash
# start.sh — Penpot single-container entrypoint.
# The PostgreSQL data directory is already initialised and seeded at build time.
# Just start all services via supervisord.
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
