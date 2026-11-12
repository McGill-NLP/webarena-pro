#!/bin/bash
NEXTCLOUD_HOST_PORT="${WP_NEXTCLOUD_HOST_PORT:-8080}"
docker exec test-nc curl -s -c /tmp/cookies.txt -X POST -d "user=admin&password=admin" "http://localhost:${NEXTCLOUD_HOST_PORT}/login"
docker exec test-nc curl -s -b /tmp/cookies.txt "http://localhost:${NEXTCLOUD_HOST_PORT}/apps/dashboard/" > /dev/null
echo "Dashboard requested"
