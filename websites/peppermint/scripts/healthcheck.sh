#!/bin/sh
# Both the frontend and login API must be ready before browser setup.
# Next.js standalone binds HOSTNAME, which Docker sets to the container name.
frontend=$(curl -sS --noproxy '*' --connect-timeout 1 --max-time 3 -o /dev/null -w '%{http_code}' "http://${HOSTNAME:-127.0.0.1}:3000/" 2>/dev/null) || frontend=000
case "$frontend" in
    2??|3??) ;;
    *) echo "Peppermint frontend not ready (HTTP $frontend)" >&2; exit 1 ;;
esac
api=$(curl -sS --noproxy '*' --connect-timeout 1 --max-time 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:5003/api/v1/auth/check 2>/dev/null) || api=000
case "$api" in
    200|401) exit 0 ;;
    *) echo "Peppermint login API not ready (HTTP $api)" >&2; exit 1 ;;
esac
