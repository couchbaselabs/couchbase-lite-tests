#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Restarting Couchbase Server..."

# Stop first
bash "$SCRIPT_DIR/stop-cbs.sh"

# Small delay to ensure clean shutdown
sleep 5

# Start
bash "$SCRIPT_DIR/start-cbs.sh"

