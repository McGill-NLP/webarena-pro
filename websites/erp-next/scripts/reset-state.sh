#!/usr/bin/env bash
set -euo pipefail

SITE_NAME="${ERPNEXT_SITE_NAME:-erpnext.localhost}"
DB_ROOT_PASSWORD="${ERPNEXT_DB_ROOT_PASSWORD:-root}"
MARIADB_SOCKET="/var/run/mysqld/mysqld.sock"
BENCH_DIR="/home/frappe/frappe-bench"
SITE_DIR="${BENCH_DIR}/sites/${SITE_NAME}"
SNAPSHOT_DIR="/opt/erpnext-seed/reset"

run_as_frappe() {
    su -s /bin/bash frappe -c "$*"
}

wait_for_mariadb() {
    local attempts=120
    while (( attempts > 0 )); do
        if mysqladmin --protocol=socket --socket="${MARIADB_SOCKET}" ping >/dev/null 2>&1; then
            return 0
        fi
        attempts=$((attempts - 1))
        sleep 1
    done
    echo "Timed out waiting for MariaDB startup" >&2
    return 1
}

detect_mysql_root_auth() {
    if mysql --protocol=socket --socket="${MARIADB_SOCKET}" -uroot -e "SELECT 1" >/dev/null 2>&1; then
        MYSQL_AUTH_ARGS=(--protocol=socket --socket="${MARIADB_SOCKET}" -uroot)
        return 0
    fi

    if mysql --protocol=socket --socket="${MARIADB_SOCKET}" -uroot -p"${DB_ROOT_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1; then
        MYSQL_AUTH_ARGS=(--protocol=socket --socket="${MARIADB_SOCKET}" -uroot -p"${DB_ROOT_PASSWORD}")
        return 0
    fi

    echo "Could not authenticate as MariaDB root." >&2
    return 1
}

site_config_value() {
    local key="$1"
    python3 - <<PY
import json
from pathlib import Path
cfg = json.loads(Path("${SITE_DIR}/site_config.json").read_text(encoding="utf-8"))
print(cfg.get("${key}", ""))
PY
}

for _i in $(seq 1 180); do
    if [[ -f "${SNAPSHOT_DIR}/ready" ]]; then
        break
    fi
    sleep 1
done

for artifact in db.sql.gz site-files.tar.gz ready; do
    if [[ ! -e "${SNAPSHOT_DIR}/${artifact}" ]]; then
        echo "Missing ERPNext reset snapshot artifact: ${SNAPSHOT_DIR}/${artifact}" >&2
        exit 1
    fi
done

wait_for_mariadb
detect_mysql_root_auth

DB_NAME="$(site_config_value db_name)"
DB_PASSWORD="$(site_config_value db_password)"
if [[ -z "$DB_NAME" || -z "$DB_PASSWORD" ]]; then
    echo "Could not determine ERPNext site database credentials." >&2
    exit 1
fi

echo "[erp-next-reset] Restoring site files..."
rm -rf "${SITE_DIR}/public" "${SITE_DIR}/private"
tar xzf "${SNAPSHOT_DIR}/site-files.tar.gz" -C "${SITE_DIR}"
find "${SITE_DIR}" \( ! -user frappe -o ! -group frappe \) -exec chown frappe:frappe {} +

if [[ -s "${SNAPSHOT_DIR}/mysql.tar.gz" ]]; then
    echo "[erp-next-reset] Restoring the clean MariaDB snapshot..."
    mysqladmin "${MYSQL_AUTH_ARGS[@]}" shutdown
    for _i in $(seq 1 60); do
        if ! mysqladmin --protocol=socket --socket="${MARIADB_SOCKET}" ping >/dev/null 2>&1; then
            break
        fi
        sleep 0.1
    done
    if mysqladmin --protocol=socket --socket="${MARIADB_SOCKET}" ping >/dev/null 2>&1; then
        echo "MariaDB did not stop; refusing to replace its data directory." >&2
        exit 1
    fi
    rm -rf /var/lib/mysql
    tar xzf "${SNAPSHOT_DIR}/mysql.tar.gz" -C /var/lib
    mkdir -p /var/run/mysqld
    chown mysql:mysql /var/run/mysqld
    mysqld_safe --datadir=/var/lib/mysql --socket="${MARIADB_SOCKET}" \
        --pid-file=/var/run/mysqld/mysqld.pid >/var/log/webarena-mariadb-reset.log 2>&1 </dev/null &
    wait_for_mariadb
    detect_mysql_root_auth
else
echo "[erp-next-reset] Recreating database ${DB_NAME}..."
mysql "${MYSQL_AUTH_ARGS[@]}" <<SQL
DROP DATABASE IF EXISTS \`${DB_NAME}\`;
CREATE DATABASE \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_NAME}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER '${DB_NAME}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_NAME}'@'localhost';
FLUSH PRIVILEGES;
SQL

gunzip -c "${SNAPSHOT_DIR}/db.sql.gz" | mysql "${MYSQL_AUTH_ARGS[@]}" "${DB_NAME}"

fi

# This container has a dedicated, nonpersistent Redis instance for cache and
# queues. Empty it as on a fresh start; avoid booting the entire bench CLI.
redis-cli FLUSHALL >/dev/null
echo "[erp-next-reset] Done."
