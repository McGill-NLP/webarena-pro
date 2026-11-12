#!/usr/bin/env sh
set -eu

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Error: neither python nor python3 is available in PATH." >&2
  exit 1
fi

# A runtime built from this source already has matching migrations and the
# complete seed database. Restore only when explicitly requested or absent.
snapshot="${JOBPORTAL_SEED_SNAPSHOT:-/opt/webarena-seed/jobportal.sqlite3}"
if [ -f "$snapshot" ] && [ "${SEED_DATA:-1}" = "1" ]; then
  if [ ! -s /app/db.sqlite3 ] || [ "${SEED_RESET:-0}" = "1" ]; then
    ${PYTHON_BIN} -c 'import django; django.setup(); from core.seed_snapshot import restore_seed_snapshot; assert restore_seed_snapshot()'
  fi
  exec "$@"
fi

${PYTHON_BIN} manage.py migrate --noinput

if [ "${SEED_DATA:-1}" = "1" ]; then
  if [ "${SEED_RESET:-0}" = "1" ]; then
    ${PYTHON_BIN} manage.py seed_demo_data --reset
    ${PYTHON_BIN} manage.py seed_kaggle_data --reset
  else
    ${PYTHON_BIN} manage.py seed_demo_data
    ${PYTHON_BIN} manage.py seed_kaggle_data
  fi
fi

exec "$@"
