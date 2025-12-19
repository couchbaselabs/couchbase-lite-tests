#!/bin/bash

CONFIG_DIR="/home/ec2-user/config"
CONFIG_NAME="${HTTP_config:-bootstrap}"
CONFIG_FILE="${CONFIG_DIR}/${CONFIG_NAME}.json"

echo "Starting Sync Gateway with config: ${CONFIG_FILE}..."

if pgrep -f "sync_gateway" > /dev/null; then
    echo "Sync Gateway is already running"
    exit 0
fi

nohup /opt/couchbase-sync-gateway/bin/sync_gateway "${CONFIG_FILE}" > /home/ec2-user/logs/sgw.log 2>&1 &
SGW_PID=$!

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
