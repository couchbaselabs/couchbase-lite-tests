#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Restarting Sync Gateway..."

bash "$SCRIPT_DIR/stop-sgw.sh"
sleep 2

# Parse config from QUERY_STRING (not HTTP_config)
CONFIG_NAME=$(echo "$QUERY_STRING" | grep -oE 'config=[^&]+' | cut -d= -f2)
export HTTP_config="${CONFIG_NAME:-bootstrap}"
bash "$SCRIPT_DIR/start-sgw.sh"