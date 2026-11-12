#!/bin/sh
set -e

PGDATA=/var/lib/postgresql/data

# Start PostgreSQL
su postgres -s /bin/sh -c "pg_ctl start -D $PGDATA -w -l /var/log/postgresql/postgresql.log -o '-k /var/run/postgresql'"

# Start backend
cd /app/backend
DATABASE_URL="postgresql://postgres@/acidwave?host=/var/run/postgresql" node src/server.js &

# Start nginx in foreground
nginx -g 'daemon off;'
