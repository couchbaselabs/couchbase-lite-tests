#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
REQUEST_BODY=$(read_http_body)

DIR=$(mktemp -d)
rm $DIR/config.json || true
echo $REQUEST_BODY > $DIR/config.json

LOG="$DIR/edge.log"
nohup /opt/couchbase-edge-server/bin/couchbase-edge-server $DIR/config.json > $LOG 2>&1 < /dev/null &
EDGE_SERVER_PID=$!
sleep 1
if kill -0 "$EDGE_SERVER_PID" 2>/dev/null; then
  echo "Edge server running"
else
  echo "Edge server failed to start:"
  cat $LOG
  exit 1
fi