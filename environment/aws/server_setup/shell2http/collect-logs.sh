#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
set -uo pipefail

LOG_DIR="/home/ec2-user/log"
CBS_LOGS_DIR_IN_CONTAINER="/opt/couchbase/var/lib/couchbase/logs"
CBCOLLECT_BIN="/opt/couchbase/bin/cbcollect_info"

REQ=$(read_http_body | jq -r '.filename // empty')
FILENAME="${REQ:-cbcollect-$(date -u +%Y%m%d-%H%M%S).zip}"

# Reject path traversal - filename is attacker-controllable in principle
FILENAME=$(basename "$FILENAME")
case "$FILENAME" in
  *.zip) ;;
  *) FILENAME="${FILENAME}.zip" ;;
esac

CBS_CONTAINER=$(sudo docker ps -a --format '{{.Names}}' | grep -E 'cbs|couchbase' | head -1)
if [ -z "$CBS_CONTAINER" ]; then
  jq -nc '{error: "CBS container not found"}'
  exit 1
fi

# Written straight into the container's own logs directory, which the host bind-mounts
# to LOG_DIR -- so the finished archive is immediately visible over Caddy, no copy step.
OUT_PATH_IN_CONTAINER="$CBS_LOGS_DIR_IN_CONTAINER/$FILENAME"
OUT_PATH_ON_HOST="$LOG_DIR/$FILENAME"

# Bounded: a stuck GSI/indexer service is exactly the case this exists to diagnose, and
# cbcollect_info has no timeout of its own -- a wedged node must not hang the whole run.
COLLECT_ERR=$(sudo docker exec "$CBS_CONTAINER" timeout 300 "$CBCOLLECT_BIN" \
  --log-redaction-level=partial \
  "$OUT_PATH_IN_CONTAINER" 2>&1)
COLLECT_RC=$?

if [ "$COLLECT_RC" -ne 0 ] || [ ! -s "$OUT_PATH_ON_HOST" ]; then
  jq -nc --arg err "$COLLECT_ERR" --argjson rc "$COLLECT_RC" \
    '{error: "failed to create archive", rc: $rc, stderr: $err}'
  exit 1
fi

SIZE=$(stat -c%s "$OUT_PATH_ON_HOST" 2>/dev/null)
jq -nc --arg file "$FILENAME" \
  --argjson size "${SIZE:-0}" \
  --arg warnings "$COLLECT_ERR" \
  '{file: $file, size: $size} + (if $warnings == "" then {} else {warnings: $warnings} end)'
