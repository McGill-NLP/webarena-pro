#!/usr/bin/env bash
set -euo pipefail

PG_BIN="/usr/lib/postgresql/15/bin"
PGDATA="${PGDATA:-/app/.pgdata}"
POSTGRES_LOG="${POSTGRES_LOG:-/tmp/postgres-runtime.log}"

start_postgres() {
  mkdir -p /var/run/postgresql
  chown postgres:postgres /var/run/postgresql "$PGDATA"

  if ! su postgres -c "$PG_BIN/pg_ctl -D '$PGDATA' status" >/dev/null 2>&1; then
    su postgres -c "$PG_BIN/pg_ctl -D '$PGDATA' -l '$POSTGRES_LOG' start"
  fi

  until "$PG_BIN/pg_isready" -h 127.0.0.1 -p 5432 -U postgres >/dev/null 2>&1; do
    sleep 1
  done
}

stop_postgres() {
  su postgres -c "$PG_BIN/pg_ctl -D '$PGDATA' stop -m fast" >/dev/null 2>&1 || true
}

command="${1:-start}"

case "$command" in
  start)
    shift || true
    start_postgres
    npm run start -- "$@" &
    app_pid=$!
    trap 'kill "$app_pid" 2>/dev/null || true; stop_postgres' EXIT INT TERM
    wait "$app_pid"
    ;;
  reset)
    shift || true
    start_postgres
    exec npm run db:reset -- "$@"
    ;;
  *)
    start_postgres
    exec "$@"
    ;;
esac
