#!/bin/bash
set -euo pipefail

SEED_TAR="/opt/webarena-seed/mysql.tar.gz"
MYSQL_DATA="/var/lib/mysql"
MYSQL_SOCKET="/run/mysqld/mysqld.sock"

if [ ! -s "$SEED_TAR" ]; then
    echo "Missing Firefly seed snapshot: $SEED_TAR" >&2
    exit 1
fi

echo "[firefly-reset] Stopping MariaDB..."
if mariadb-admin --socket="$MYSQL_SOCKET" -uroot ping --silent >/dev/null 2>&1; then
    mariadb-admin --socket="$MYSQL_SOCKET" -uroot shutdown >/dev/null 2>&1 || true
fi

for _i in $(seq 1 30); do
    if ! mariadb-admin --socket="$MYSQL_SOCKET" -uroot ping --silent >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

pkill -TERM mariadbd >/dev/null 2>&1 || true
sleep 1

echo "[firefly-reset] Restoring MariaDB data..."
rm -rf "$MYSQL_DATA"
mkdir -p "$MYSQL_DATA" /run/mysqld
tar xzf "$SEED_TAR" -C /var/lib
chown -R mysql:mysql "$MYSQL_DATA" /run/mysqld

echo "[firefly-reset] Restarting MariaDB..."
mariadbd --user=mysql \
    --datadir="$MYSQL_DATA" \
    --socket="$MYSQL_SOCKET" \
    --pid-file=/run/mysqld/mysqld.pid \
    --bind-address=127.0.0.1 \
    --log-error="$MYSQL_DATA/mariadb-error.log" &

for i in $(seq 1 60); do
    if mariadb-admin --socket="$MYSQL_SOCKET" ping --silent >/dev/null 2>&1; then
        echo "[firefly-reset] MariaDB ready after ${i}s"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "Timed out waiting for MariaDB after reset" >&2
        exit 1
    fi
    sleep 1
done

chown -R www-data:www-data /var/www/html/storage
echo "[firefly-reset] Done."
