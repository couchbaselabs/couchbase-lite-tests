#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

setsid /home/ec2-user/shell2http/shell2http -no-index -cgi -500 -port 20002 \
/start-sgw $SCRIPT_DIR/start-sgw.sh \
/stop-sgw $SCRIPT_DIR/stop-sgw.sh \
/restart-sgw $SCRIPT_DIR/restart-sgw.sh \
/status $SCRIPT_DIR/status.sh > /dev/null 2>&1 &

