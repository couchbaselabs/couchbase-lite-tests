#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

setsid /home/ec2-user/shell2http/shell2http -no-index -cgi -500 -port 20001 \
/add-user $SCRIPT_DIR/add-user.sh \
/firewall $SCRIPT_DIR/firewall.sh \
/kill-edgeserver $SCRIPT_DIR/kill-edgeserver.sh \
/reset-db $SCRIPT_DIR/reset-db.sh /start-edgeserver \
$SCRIPT_DIR/start-edgeserver.sh > /dev/null 2>&1 &

chmod +x /home/ec2-user/shell2http/add-user.sh
chmod +x /home/ec2-user/shell2http/start-edgeserver.sh
chmod +x /home/ec2-user/shell2http/kill-edgeserver.sh
chmod +x /home/ec2-user/shell2http/firewall.sh
chmod +x /home/ec2-user/shell2http/reset-db.sh
chmod +x /home/ec2-user/shell2http/common.sh