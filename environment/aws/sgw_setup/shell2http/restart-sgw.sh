#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Restarting Sync Gateway..."

bash "$SCRIPT_DIR/stop-sgw.sh"
sleep 2

# Pass the config parameter if provided
export HTTP_config="${HTTP_config:-bootstrap}"
bash "$SCRIPT_DIR/start-sgw.sh"
