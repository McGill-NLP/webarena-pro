#!/bin/bash
# Custom entrypoint: starts MariaDB from baked-in data, then hands off to
# Firefly's default entrypoint. Runtime reset restores MariaDB from the
# immutable snapshot at /opt/webarena-seed/mysql.tar.gz.

set -e

echo "[firefly-seeded] Starting MariaDB…"

mkdir -p /run/mysqld
chown mysql:mysql /run/mysqld

mariadbd --user=mysql \
    --datadir=/var/lib/mysql \
    --socket=/run/mysqld/mysqld.sock \
    --pid-file=/run/mysqld/mysqld.pid \
    --bind-address=127.0.0.1 \
    --log-error=/var/lib/mysql/mariadb-error.log &

for i in $(seq 1 60); do
    if mariadb-admin --socket=/run/mysqld/mysqld.sock ping --silent >/dev/null 2>&1; then
        echo "[firefly-seeded] MariaDB ready after ${i}s"
        break
    fi
    sleep 1
done

if ! mariadb --socket=/run/mysqld/mysqld.sock -ufirefly -psecret_firefly_password firefly -e "SELECT 1;" >/dev/null 2>&1; then
    echo "[firefly-seeded] ERROR: firefly database is not accessible"
    cat /var/lib/mysql/mariadb-error.log 2>/dev/null || true
    exit 1
fi

echo "[firefly-seeded] Ensuring storage tree is writable by www-data"
chown -R www-data:www-data /var/www/html/storage

echo "[firefly-seeded] Handing off to Firefly entrypoint"
FAKETIME_LIB="$(find /usr/lib -path '*/faketime/libfaketime.so.1' -print -quit)"
if [ -z "$FAKETIME_LIB" ]; then
    echo "[firefly-seeded] ERROR: libfaketime was not found"
    exit 1
fi
export LD_PRELOAD="$FAKETIME_LIB"
export FAKETIME_DONT_FAKE_MONOTONIC=1
exec docker-php-serversideup-entrypoint "$@"
