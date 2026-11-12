#!/bin/bash
# healthcheck.sh — Penpot single-container health probe.
# Returns 0 if the Penpot API is responding, 1 otherwise.

STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    http://localhost:9001/api/rpc/command/get-profile 2>/dev/null || echo "0")

# 401 = server up, not authenticated — that's healthy
# 200 = server up, authenticated
if [ "$STATUS" = "200" ] || [ "$STATUS" = "401" ] || [ "$STATUS" = "403" ]; then
    exit 0
fi

exit 1
