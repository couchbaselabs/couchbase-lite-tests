#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Kill any existing shell2http server process to avoid port conflict -- see server_setup's
# shell2http/start.sh for why this matters.
pkill -x shell2http 2>/dev/null || true
sleep 2

WRAP="$SCRIPT_DIR/with-timeout.sh"
setsid /home/ec2-user/shell2http/shell2http -no-index -cgi -500 -port 20001 \
  /start-sgw "$WRAP $SCRIPT_DIR/start-sgw.sh" \
  /stop-sgw "$WRAP $SCRIPT_DIR/stop-sgw.sh" \
  /restart-sgw "$WRAP $SCRIPT_DIR/restart-sgw.sh" \
  /upload-cert "$WRAP $SCRIPT_DIR/upload-cert.sh" >/dev/null 2>&1 &
