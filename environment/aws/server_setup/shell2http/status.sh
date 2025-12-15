#!/bin/bash

echo "=== Couchbase Server Status ==="

# Check if API is responding
if curl -s --connect-timeout 2 http://localhost:8091/ > /dev/null 2>&1; then
    echo "Web UI (8091): Responding"
    
    # Get cluster status
    STATUS=$(curl -s -u Administrator:password http://localhost:8091/pools/default 2>/dev/null)
    if [[ -n "$STATUS" ]]; then
        echo "Cluster: Accessible"
        # Extract node count
        NODE_COUNT=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('nodes',[])))" 2>/dev/null)
        if [[ -n "$NODE_COUNT" ]]; then
            echo "Nodes in cluster: $NODE_COUNT"
        fi
    else
        echo "Cluster: Not accessible (auth failed?)"
    fi
else
    echo "Web UI (8091): Not responding"
    echo "Status: Stopped or unreachable"
fi

# Check Docker container status
CONTAINER_ID=$(docker ps -q --filter "ancestor=couchbase/server" 2>/dev/null)
if [[ -n "$CONTAINER_ID" ]]; then
    echo "Docker container: Running ($CONTAINER_ID)"
else
    STOPPED_CONTAINER=$(docker ps -aq --filter "ancestor=couchbase/server" 2>/dev/null)
    if [[ -n "$STOPPED_CONTAINER" ]]; then
        echo "Docker container: Stopped ($STOPPED_CONTAINER)"
    fi
fi

