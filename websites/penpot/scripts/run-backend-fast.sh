#!/bin/bash
set -euo pipefail

startup_opts="${PENPOT_FAST_JVM_OPTS:--XX:+UseSerialGC -XX:TieredStopAtLevel=1 -Djava.awt.headless=true}"
cds_archive="/opt/penpot/backend/penpot-cds.jsa"

if [ -s "$cds_archive" ]; then
    startup_opts="${startup_opts} -XX:SharedArchiveFile=${cds_archive}"
fi

export JVM_OPTS="${startup_opts} ${JVM_OPTS:-}"
exec /opt/penpot/backend/run.sh "$@"
