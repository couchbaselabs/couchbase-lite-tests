#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

setsid /home/ec2-user/shell2http/shell2http -no-index -cgi -500 -port 20001 \
/firewall $SCRIPT_DIR/firewall.sh \
/kill-edgeserver $SCRIPT_DIR/kill-edgeserver.sh \
/reset-db $SCRIPT_DIR/reset-db.sh /start-edgeserver \
$SCRIPT_DIR/start-edgeserver.sh > /dev/null 2>&1 &