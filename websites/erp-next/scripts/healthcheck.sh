#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${ERPNEXT_BASE_URL:-http://127.0.0.1:8000}"
SEED_MARKER="/home/frappe/frappe-bench/sites/.webarena_erpnext_seeded"

test -f "${SEED_MARKER}"
curl -fsS "${BASE_URL}/login" >/dev/null
