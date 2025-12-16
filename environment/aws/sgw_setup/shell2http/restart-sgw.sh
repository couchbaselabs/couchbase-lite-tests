#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pass through config parameter if provided
CONFIG_NAME="${HTTP_config:-bootstrap}"

echo "Restarting Sync Gateway with config: ${CONFIG_NAME}.json"

# Stop first
bash "$SCRIPT_DIR/stop-sgw.sh"

# Small delay to ensure clean shutdown
sleep 2

# Start with config (export for start-sgw.sh to use)
export HTTP_config="$CONFIG_NAME"
bash "$SCRIPT_DIR/start-sgw.sh"

