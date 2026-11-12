#!/usr/bin/env bash
set -euo pipefail

SITE_NAME="${ERPNEXT_SITE_NAME:-erpnext.localhost}"
BASE_URL="${ERPNEXT_BASE_URL:-http://127.0.0.1:8000}"
ADMIN_USERNAME="${ERPNEXT_ADMIN_USERNAME:-Administrator}"
ADMIN_PASSWORD="${ERPNEXT_ADMIN_PASSWORD:-admin}"
DB_ROOT_PASSWORD="${ERPNEXT_DB_ROOT_PASSWORD:-root}"
MARIADB_SOCKET="/var/run/mysqld/mysqld.sock"
BENCH_DIR="/home/frappe/frappe-bench"
SITE_DIR="/home/frappe/frappe-bench/sites/${SITE_NAME}"
SITE_MARKER="${SITE_DIR}/.webarena_site_bootstrapped"
SEED_MARKER="/home/frappe/frappe-bench/sites/.webarena_erpnext_seeded"
ERP_PID=""
MARIADB_PID=""

run_as_frappe() {
    su -s /bin/bash frappe -c "$*"
}

cleanup_services() {
    if [[ -n "${ERP_PID}" ]] && kill -0 "${ERP_PID}" >/dev/null 2>&1; then
        kill "${ERP_PID}" >/dev/null 2>&1 || true
        wait "${ERP_PID}" >/dev/null 2>&1 || true
    fi

    redis-cli shutdown nosave >/dev/null 2>&1 || true

    if mysqladmin --protocol=socket --socket="${MARIADB_SOCKET}" ping >/dev/null 2>&1; then
        if detect_mysql_root_auth >/dev/null 2>&1; then
            mysqladmin "${MYSQL_AUTH_ARGS[@]}" shutdown >/dev/null 2>&1 || true
        fi
    elif [[ -n "${MARIADB_PID}" ]] && kill -0 "${MARIADB_PID}" >/dev/null 2>&1; then
        kill "${MARIADB_PID}" >/dev/null 2>&1 || true
        wait "${MARIADB_PID}" >/dev/null 2>&1 || true
    fi
    rm -f /var/run/mysqld/mysqld.sock /var/run/mysqld/mysqld.pid
}

wait_for_http_ready() {
    local attempts=180
    local url="$1"
    while (( attempts > 0 )); do
        if curl -fsS "${url}" >/dev/null 2>&1; then
            return 0
        fi
        attempts=$((attempts - 1))
        sleep 2
    done

    echo "Timed out waiting for HTTP readiness at ${url}" >&2
    return 1
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

    echo "Could not authenticate as MariaDB root with provided credentials." >&2
    return 1
}

start_mariadb() {
    mkdir -p /var/run/mysqld /var/lib/mysql
    chown mysql:mysql /var/run/mysqld /var/lib/mysql
    # Avoid copying every baked database file into the writable layer just to
    # reapply ownership that is already correct.
    find /var/lib/mysql \( ! -user mysql -o ! -group mysql \) -exec chown mysql:mysql {} +

    if [[ ! -d /var/lib/mysql/mysql ]]; then
        mariadb-install-db --user=mysql --datadir=/var/lib/mysql >/dev/null
    fi

    mysqld_safe --datadir=/var/lib/mysql --socket="${MARIADB_SOCKET}" --pid-file=/var/run/mysqld/mysqld.pid &
    MARIADB_PID=$!

    wait_for_mariadb
    detect_mysql_root_auth

    mysql "${MYSQL_AUTH_ARGS[@]}" <<SQL
CREATE USER IF NOT EXISTS 'root'@'localhost' IDENTIFIED BY '${DB_ROOT_PASSWORD}';
ALTER USER 'root'@'localhost' IDENTIFIED BY '${DB_ROOT_PASSWORD}';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' WITH GRANT OPTION;
CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY '${DB_ROOT_PASSWORD}';
ALTER USER 'root'@'127.0.0.1' IDENTIFIED BY '${DB_ROOT_PASSWORD}';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;
FLUSH PRIVILEGES;
SQL

    # Root may have been authenticated without a password before ALTER USER.
    # Re-detect credentials so subsequent mysql calls use the working auth mode.
    detect_mysql_root_auth
}

start_redis() {
    redis-server --save "" --appendonly no --daemonize yes
}

get_site_db_name() {
    local site_config_path="${SITE_DIR}/site_config.json"

    if [[ ! -f "${site_config_path}" ]]; then
        return 1
    fi

    python3 - <<PY
import json
from pathlib import Path
cfg = json.loads(Path('${site_config_path}').read_text(encoding='utf-8'))
print(cfg.get('db_name', ''))
PY
}

bootstrap_site_once() {
    if [[ -f "${SITE_MARKER}" ]]; then
        echo "Site already bootstrapped, skipping local setup steps."
        return 0
    fi

    echo "Bootstrapping ERPNext local site via bench ..."

    run_as_frappe "cd ${BENCH_DIR} && bench set-config -g db_host 127.0.0.1"
    run_as_frappe "cd ${BENCH_DIR} && bench set-config -g redis_cache redis://127.0.0.1:6379"
    run_as_frappe "cd ${BENCH_DIR} && bench set-config -g redis_queue redis://127.0.0.1:6379"
    run_as_frappe "cd ${BENCH_DIR} && bench set-config -g redis_socketio redis://127.0.0.1:6379"
    run_as_frappe "cd ${BENCH_DIR} && bench set-config -g dns_multitenant off"

    if [[ ! -d "${SITE_DIR}" ]]; then
        run_as_frappe "cd ${BENCH_DIR} && bench new-site ${SITE_NAME} --admin-password ${ADMIN_PASSWORD} --db-root-username root --db-root-password ${DB_ROOT_PASSWORD} --db-host localhost"
    fi

    # Local setup docs include "bench get-app", but this base image already ships apps/erpnext.
    # Skip get-app when directory exists to keep startup non-interactive.
    if [[ ! -d "${BENCH_DIR}/apps/erpnext" ]]; then
        run_as_frappe "cd ${BENCH_DIR} && bench get-app https://github.com/frappe/erpnext"
    fi

    if ! run_as_frappe "cd ${BENCH_DIR} && bench --site ${SITE_NAME} list-apps" | grep -qx "erpnext"; then
        run_as_frappe "cd ${BENCH_DIR} && bench --site ${SITE_NAME} install-app erpnext"
    fi

    configure_initial_defaults

    run_as_frappe "cd ${BENCH_DIR} && bench use ${SITE_NAME}"

    touch "${SITE_MARKER}"
}

configure_initial_defaults() {
    local site_db_name
    local current_fiscal_year

    site_db_name="$(get_site_db_name || true)"

    if [[ -z "${site_db_name}" ]]; then
        echo "Could not determine ERPNext DB name, skipping default setup values." >&2
        return 0
    fi

    current_fiscal_year="$(date +%Y)"

    detect_mysql_root_auth

    mysql "${MYSQL_AUTH_ARGS[@]}" "${site_db_name}" <<SQL
INSERT INTO \`tabSingles\` (\`doctype\`, \`field\`, \`value\`) VALUES ('System Settings', 'setup_complete', '1')
    ON DUPLICATE KEY UPDATE \`value\` = VALUES(\`value\`);
INSERT INTO \`tabSingles\` (\`doctype\`, \`field\`, \`value\`) VALUES ('System Settings', 'language', 'en')
    ON DUPLICATE KEY UPDATE \`value\` = VALUES(\`value\`);
INSERT INTO \`tabSingles\` (\`doctype\`, \`field\`, \`value\`) VALUES ('System Settings', 'country', 'France')
    ON DUPLICATE KEY UPDATE \`value\` = VALUES(\`value\`);
INSERT INTO \`tabSingles\` (\`doctype\`, \`field\`, \`value\`) VALUES ('System Settings', 'time_zone', 'Europe/Paris')
    ON DUPLICATE KEY UPDATE \`value\` = VALUES(\`value\`);
INSERT INTO \`tabSingles\` (\`doctype\`, \`field\`, \`value\`) VALUES ('Global Defaults', 'default_currency', 'EUR')
    ON DUPLICATE KEY UPDATE \`value\` = VALUES(\`value\`);
INSERT INTO \`tabSingles\` (\`doctype\`, \`field\`, \`value\`) VALUES ('Global Defaults', 'current_fiscal_year', '${current_fiscal_year}')
    ON DUPLICATE KEY UPDATE \`value\` = VALUES(\`value\`);
DELETE FROM \`tabDefaultValue\`
    WHERE \`parent\` = '__default' AND \`defkey\` = 'desktop:home_page';
INSERT INTO \`tabDefaultValue\` (
    \`name\`, \`creation\`, \`modified\`, \`modified_by\`, \`owner\`, \`docstatus\`, \`idx\`,
    \`parent\`, \`parentfield\`, \`parenttype\`, \`defkey\`, \`defvalue\`
) VALUES (
    'webarena-desktop-home-page', NOW(), NOW(), 'Administrator', 'Administrator', 0, 0,
    '__default', 'system_defaults', '__default', 'desktop:home_page', 'workspace'
);
UPDATE \`tabUser\`
    SET \`language\` = 'en'
    WHERE COALESCE(\`language\`, '') = '';
UPDATE \`tabDashboard Chart\`
    SET \`filters_json\` = '{"period":"Monthly","based_on":"Item","company":"WebArena Corp","fiscal_year":"${current_fiscal_year}"}'
    WHERE \`name\` = 'Purchase Order Trends';
UPDATE \`tabDashboard Chart\`
    SET \`filters_json\` = '{"period":"Monthly","based_on":"Item","company":"WebArena Corp","fiscal_year":"${current_fiscal_year}"}'
    WHERE \`name\` = 'Sales Order Trends';
SQL

    echo "Applied initial System Settings/Global Defaults values."
}

configure_login_home_route() {
    local site_db_name

    site_db_name="$(get_site_db_name || true)"

    if [[ -z "${site_db_name}" ]]; then
        echo "Could not determine ERPNext DB name, skipping login home route setup." >&2
        return 0
    fi

    detect_mysql_root_auth

    mysql "${MYSQL_AUTH_ARGS[@]}" "${site_db_name}" <<SQL
UPDATE \`tabUser\`
    SET \`default_workspace\` = 'Home'
    WHERE \`enabled\` = 1 AND \`user_type\` = 'System User';
DELETE FROM \`tabDefaultValue\`
    WHERE \`parent\` = '__default' AND \`defkey\` = 'desktop:home_page';
INSERT INTO \`tabDefaultValue\` (
    \`name\`, \`creation\`, \`modified\`, \`modified_by\`, \`owner\`, \`docstatus\`, \`idx\`,
    \`parent\`, \`parentfield\`, \`parenttype\`, \`defkey\`, \`defvalue\`
) VALUES (
    'webarena-desktop-home-page', NOW(), NOW(), 'Administrator', 'Administrator', 0, 0,
    '__default', 'system_defaults', '__default', 'desktop:home_page', 'workspace'
);
SQL

    echo "Configured ERPNext login home route."
}

start_erpnext_web() {
    # Bench local setup expects a running server process.
    run_as_frappe "cd ${BENCH_DIR} && bench --site ${SITE_NAME} serve --port 8000 --noreload" &
    ERP_PID=$!
}

wait_for_erpnext() {
    wait_for_http_ready "${BASE_URL}/api/method/ping"
}

run_seed_once() {
    if [[ -f "${SEED_MARKER}" ]]; then
        echo "Seed already applied, skipping."
        return 0
    fi

    echo "Applying ERPNext seed data ..."
    python3 /opt/erpnext-seed/seed_erpnext.py \
        --base-url "${BASE_URL}" \
        --admin-username "${ADMIN_USERNAME}" \
        --admin-password "${ADMIN_PASSWORD}" \
        --seed-file /opt/erpnext-seed/seed_data.json

    touch "${SEED_MARKER}"
    echo "Seed data applied."
}

create_seed_snapshot_once() {
    local snapshot_dir="/opt/erpnext-seed/reset"
    local site_db_name

    if [[ -f "${snapshot_dir}/ready" ]]; then
        echo "ERPNext reset snapshot already exists, skipping."
        return 0
    fi

    site_db_name="$(get_site_db_name || true)"
    if [[ -z "${site_db_name}" ]]; then
        echo "Could not determine ERPNext DB name, cannot create reset snapshot." >&2
        return 1
    fi

    detect_mysql_root_auth
    mkdir -p "${snapshot_dir}"

    echo "Creating ERPNext reset database snapshot..."
    mysqldump "${MYSQL_AUTH_ARGS[@]}" \
        --single-transaction \
        --routines \
        --triggers \
        "${site_db_name}" \
        | gzip > "${snapshot_dir}/db.sql.gz.tmp"
    mv "${snapshot_dir}/db.sql.gz.tmp" "${snapshot_dir}/db.sql.gz"

    echo "Creating ERPNext reset file snapshot..."
    tar czf "${snapshot_dir}/site-files.tar.gz.tmp" \
        -C "${SITE_DIR}" \
        public \
        private \
        site_config.json
    mv "${snapshot_dir}/site-files.tar.gz.tmp" "${snapshot_dir}/site-files.tar.gz"
    touch "${snapshot_dir}/ready"
    echo "ERPNext reset snapshot created."
}

main() {
    trap cleanup_services EXIT
    trap 'exit 0' INT TERM

    start_mariadb
    start_redis
    bootstrap_site_once
    start_erpnext_web

    wait_for_erpnext
    if [[ ! -f "/opt/erpnext-seed/reset/ready" ]]; then
        run_seed_once
        configure_login_home_route
        run_as_frappe "cd ${BENCH_DIR} && bench --site ${SITE_NAME} clear-cache"
        create_seed_snapshot_once
    else
        echo "ERPNext preseeded snapshot found, skipping runtime seed steps."
    fi

    if [[ "${WEBARENA_ERPNEXT_SEED_ONLY:-0}" == "1" ]]; then
        # A clean physical snapshot restores hundreds of ERPNext tables much
        # faster than replaying their SQL definitions for every episode.
        cleanup_services
        tar czf /opt/erpnext-seed/reset/mysql.tar.gz.tmp -C /var/lib mysql
        mv /opt/erpnext-seed/reset/mysql.tar.gz.tmp /opt/erpnext-seed/reset/mysql.tar.gz
        echo "ERPNext seed-only mode complete."
        return 0
    fi

    wait "${ERP_PID}"
}

main "$@"
