#!/bin/bash

echo "Stopping Couchbase Server..."

# Stop the couchbase-server service
sudo systemctl stop couchbase-server 2>/dev/null

# Also try docker stop if running in container
CONTAINER_ID=$(docker ps -q --filter "ancestor=couchbase/server" 2>/dev/null)
if [[ -n "$CONTAINER_ID" ]]; then
    echo "Stopping Couchbase Docker container: $CONTAINER_ID"
    docker stop $CONTAINER_ID
fi

# Verify stopped
sleep 2
if curl -s --connect-timeout 2 http://localhost:8091/ > /dev/null 2>&1; then
    echo "WARNING: Couchbase Server still responding on port 8091"
    exit 1
else
    echo "Couchbase Server stopped successfully"
fi

