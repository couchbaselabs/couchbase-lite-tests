#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Restarting Sync Gateway..."

# Stop first
bash "$SCRIPT_DIR/stop-sgw.sh"

# Small delay to ensure clean shutdown
sleep 2

# Start
bash "$SCRIPT_DIR/start-sgw.sh"

