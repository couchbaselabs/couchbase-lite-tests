#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

setsid /home/ec2-user/shell2http/shell2http -no-index -cgi -500 -port 20003 \
/start-cbs $SCRIPT_DIR/start-cbs.sh \
/stop-cbs $SCRIPT_DIR/stop-cbs.sh \
/restart-cbs $SCRIPT_DIR/restart-cbs.sh \
/status $SCRIPT_DIR/status.sh > /dev/null 2>&1 &

