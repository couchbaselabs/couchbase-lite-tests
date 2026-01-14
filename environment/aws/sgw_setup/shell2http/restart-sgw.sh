#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

echo "Restarting Sync Gateway..."

# Read config name from POST body (first line)
BODY=$(read_http_body)
CONFIG_VALUE=$(echo "$BODY" | head -n 1)

# Use default if empty
CONFIG_VALUE="${CONFIG_VALUE:-bootstrap}"
echo "DEBUG: Config name: ${CONFIG_VALUE}"

bash "$SCRIPT_DIR/stop-sgw.sh"
sleep 2

# Export for start-sgw.sh
export HTTP_config="$CONFIG_VALUE"
bash "$SCRIPT_DIR/start-sgw.sh"
