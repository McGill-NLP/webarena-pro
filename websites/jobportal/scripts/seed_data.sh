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

RESET_FLAG=""
if [ "${1:-}" = "--reset" ]; then
  RESET_FLAG="--reset"
fi

${PYTHON_BIN} manage.py migrate --noinput
${PYTHON_BIN} manage.py seed_demo_data ${RESET_FLAG}
${PYTHON_BIN} manage.py seed_kaggle_data ${RESET_FLAG}
