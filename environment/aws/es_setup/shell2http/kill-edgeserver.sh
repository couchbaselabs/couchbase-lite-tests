#!/bin/bash

PID=$(ps -ax | grep [e]dge-server | awk '{print $1}')
if [[ "$PID" == "" ]]; then
    echo "Running process not found"
    exit 0
fi

sudo kill -SIGHUP $PID
if curl -fs "http://127.0.0.1:59840" >/dev/null 2>&1; then
  echo "Edge server is still running"
  PIDS=$(pgrep -f "/opt/couchbase-edge-server/bin/couchbase-edge-server" || true)
  kill -TERM $PIDS || true
fi