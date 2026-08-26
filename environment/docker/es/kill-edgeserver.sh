#!/bin/bash

PIDS=$(pgrep -f "/opt/couchbase-edge-server/bin/couchbase-edge-server" || true)
if [[ -z "$PIDS" ]]; then
    echo "Running process not found"
    exit 0
fi

kill -TERM $PIDS || true
sleep 1
PIDS=$(pgrep -f "/opt/couchbase-edge-server/bin/couchbase-edge-server" || true)
if [[ -n "$PIDS" ]]; then
    kill -KILL $PIDS || true
fi
echo "Edge server stopped"
