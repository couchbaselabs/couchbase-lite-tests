#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Kill any existing shell2http server process to avoid port conflict
pkill -x shell2http 2>/dev/null || true
sleep 2

WRAP="$SCRIPT_DIR/with-timeout.sh"
setsid /home/ec2-user/shell2http/shell2http -no-index -cgi -500 -port 20001 \
  /add-user "$WRAP $SCRIPT_DIR/add-user.sh" \
  /firewall "$WRAP $SCRIPT_DIR/firewall.sh" \
  /kill-edgeserver "$WRAP $SCRIPT_DIR/kill-edgeserver.sh" \
  /reset-db "$WRAP $SCRIPT_DIR/reset-db.sh" \
  /reset-all-dbs "$WRAP $SCRIPT_DIR/reset-all-dbs.sh" \
  /start-edgeserver "$WRAP $SCRIPT_DIR/start-edgeserver.sh" \
  /collect-logs "$WRAP $SCRIPT_DIR/collect-logs.sh" \
  /write-file "$WRAP $SCRIPT_DIR/write-file.sh" >/dev/null 2>&1 &

chmod +x /home/ec2-user/shell2http/add-user.sh
chmod +x /home/ec2-user/shell2http/start-edgeserver.sh
chmod +x /home/ec2-user/shell2http/kill-edgeserver.sh
chmod +x /home/ec2-user/shell2http/firewall.sh
chmod +x /home/ec2-user/shell2http/reset-db.sh
chmod +x /home/ec2-user/shell2http/reset-all-dbs.sh
chmod +x /home/ec2-user/shell2http/common.sh
chmod +x /home/ec2-user/shell2http/write-file.sh
chmod +x /home/ec2-user/shell2http/collect-logs.sh
chmod +x /home/ec2-user/shell2http/with-timeout.sh
