#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

echo "Starting Couchbase Server..."

# Check if already running
if curl -s --connect-timeout 2 http://localhost:8091/ > /dev/null 2>&1; then
    echo "Couchbase Server is already running"
    exit 0
fi

# Try systemctl first
if systemctl is-enabled couchbase-server 2>/dev/null; then
    echo "Starting via systemctl..."
    sudo systemctl start couchbase-server
else
    # Try docker
    CONTAINER_ID=$(docker ps -aq --filter "ancestor=couchbase/server" 2>/dev/null | head -1)
    if [[ -n "$CONTAINER_ID" ]]; then
        echo "Starting Docker container: $CONTAINER_ID"
        docker start $CONTAINER_ID
    else
        echo "ERROR: No Couchbase Server installation found"
        exit 1
    fi
fi

# Wait for it to be ready
echo "Waiting for Couchbase Server to start..."
for i in {1..60}; do
    if curl -s --connect-timeout 2 http://localhost:8091/ui/index.html > /dev/null 2>&1; then
        echo "Couchbase Server started successfully"
        exit 0
    fi
    sleep 2
done

echo "ERROR: Couchbase Server failed to start within 120 seconds"
exit 1

