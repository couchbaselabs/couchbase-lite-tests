#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Read port from JSON body
REQUEST_BODY=$(read_http_body)
PORT=$(echo "$REQUEST_BODY" | jq -r '.port // 8091')

echo "Starting CBS..."

CBS_CONTAINER=$(sudo docker ps -a --format '{{.Names}}' | grep -E 'cbs|couchbase' | head -1)
if [ -z "$CBS_CONTAINER" ]; then
    echo "ERROR: CBS container not found"
    exit 1
fi

sudo docker exec "$CBS_CONTAINER" sv start /etc/service/couchbase-server

# Wait for CBS to be ready
TIMEOUT=60
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/pools/default" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "CBS started successfully on port $PORT"
        exit 0
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

echo "ERROR: CBS did not start within ${TIMEOUT}s"
exit 1