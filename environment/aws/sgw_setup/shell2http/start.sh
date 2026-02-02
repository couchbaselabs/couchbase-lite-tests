#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

setsid /home/ec2-user/shell2http/shell2http -no-index -cgi -500 -port 20001 \
/start-sgw "bash $SCRIPT_DIR/start-sgw.sh" \
/stop-sgw "bash $SCRIPT_DIR/stop-sgw.sh" \
/restart-sgw "bash $SCRIPT_DIR/restart-sgw.sh" \
/upload-cert "bash $SCRIPT_DIR/upload-cert.sh" > /dev/null 2>&1 &
