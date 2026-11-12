#!/bin/bash
# Health check: verify nginx is serving Roundcube (HTTP 200 or 302 on /)
curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1/ | grep -qE "^(200|302)$"
