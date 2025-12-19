#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

setsid /home/ec2-user/shell2http/shell2http -no-index -cgi -500 -port 20001 \
/start-sgw "bash $SCRIPT_DIR/start-sgw.sh" \
/stop-sgw "bash $SCRIPT_DIR/stop-sgw.sh" \
/restart-sgw "bash $SCRIPT_DIR/restart-sgw.sh" \
/status "bash $SCRIPT_DIR/status.sh" > /dev/null 2>&1 &

# Wait for shell2http to start
sleep 2

# Check if port 20001 is listening
if ss -lnt sport = :20001 | grep -q LISTEN; then
    echo "shell2http started on port 20001 (log: /home/ec2-user/logs/shell2http.log)"
else
    echo "ERROR: shell2http failed to start or bind to port 20001"
    exit 1
fi
