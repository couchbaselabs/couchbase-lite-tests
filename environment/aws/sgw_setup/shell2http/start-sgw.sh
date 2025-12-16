#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

CONFIG_DIR="/home/ec2-user/config"

# Support config parameter: ?config=alternate uses bootstrap-alternate.json
# Default is bootstrap.json
CONFIG_NAME="${HTTP_config:-bootstrap}"
BOOTSTRAP_CONFIG_FILE="${CONFIG_DIR}/${CONFIG_NAME}.json"

if [ ! -f "$BOOTSTRAP_CONFIG_FILE" ]; then
    echo "ERROR: Config file not found: $BOOTSTRAP_CONFIG_FILE"
    exit 1
fi

echo "Starting Sync Gateway with config: ${CONFIG_NAME}.json"

# Check if already running
if pgrep -f "sync_gateway" > /dev/null; then
    echo "Sync Gateway is already running"
    exit 0
fi

# Start SG in background
nohup /opt/couchbase-sync-gateway/bin/sync_gateway "${BOOTSTRAP_CONFIG_FILE}" > /home/ec2-user/logs/sgw.log 2>&1 &
SGW_PID=$!

# Wait for it to be ready
echo "Waiting for Sync Gateway to start (PID: $SGW_PID)..."
for i in {1..30}; do
    if curl -sk --connect-timeout 2 https://localhost:4984/ > /dev/null 2>&1; then
        echo "Sync Gateway started successfully"
        exit 0
    fi
    sleep 2
done

echo "ERROR: Sync Gateway failed to start within 60 seconds"
exit 1

