#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
REQUEST_BODY=$(read_http_body)

DIRLOG="/home/ec2-user/log"
DIR="/opt/couchbase-edge-server/etc"
if [[ -n "$REQUEST_BODY" && "$REQUEST_BODY" != "{}" ]]; then
  echo "New config received. Updating config.json"
  rm -f "$DIR/config.json" || true
  echo "$REQUEST_BODY" > "$DIR/config.json"
else
  echo "No new config provided. Using existing config.json"
fi

LOG="$DIRLOG/edge.log"
setsid /opt/couchbase-edge-server/bin/couchbase-edge-server $DIR/config.json > $LOG 2>&1 < /dev/null &
disown
EDGE_SERVER_PID=$!
sleep 1
if kill -0 "$EDGE_SERVER_PID" 2>/dev/null; then
  echo "Edge server running"
else
  echo "Edge server failed to start:"
  cat $LOG
  exit 1
fi