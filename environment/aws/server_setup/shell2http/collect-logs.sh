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
  # Always exit 0: shell2http (running -cgi -500) discards this script's own stdout on a
  # non-zero exit and substitutes a generic "exec error: exit status N" instead, so the only
  # way the caller ever sees this JSON -- success or failure -- is if we exit 0 regardless.
  jq -nc '{error: "CBS container not found"}'
  exit 0
fi

# Written straight into the container's own logs directory, which the host bind-mounts
# to LOG_DIR -- so the finished archive is immediately visible over Caddy, no copy step.
OUT_PATH_IN_CONTAINER="$CBS_LOGS_DIR_IN_CONTAINER/$FILENAME"
OUT_PATH_ON_HOST="$LOG_DIR/$FILENAME"
# --log-redaction-level writes the redacted copy to a second, "-redacted" suffixed file
# alongside the plain one -- the plain one stays fully unredacted. This is the file we
# actually want to serve.
REDACTED_FILENAME="${FILENAME%.zip}-redacted.zip"
OUT_PATH_ON_HOST_REDACTED="$LOG_DIR/$REDACTED_FILENAME"

# The host outlives the run and nothing else prunes this directory, so keeping every past
# archive fills the disk. Only prune this endpoint's own naming scheme -- LOG_DIR also holds
# CBS's live logs, so it can't be wiped wholesale the way the Edge Server sibling does.
rm -f "$LOG_DIR"/cbcollect-*.zip

# Bounded: a stuck GSI/indexer service is exactly the case this exists to diagnose, and
# cbcollect_info has no timeout of its own -- a wedged node must not hang the whole run.
# 1200s (20m): cbcollect_info on a cluster with real data volume (thousands of per-vBucket
# couchstore dumps, stats snapshots, etc.) routinely runs well past a few minutes -- a short
# budget here kills a collection that was simply still working, not actually stuck.
# --kill-after=30: plain `timeout` only sends SIGTERM at the deadline, which a wedged or
# mid-write cbcollect_info can ignore or outlive -- escalate to SIGKILL if it's still
# running 30s later, rather than let docker exec (and this request) hang indefinitely.
# stdout carries cbcollect_info's own progress/status noise, not diagnostics -- discard it
# so only real stderr ends up in COLLECT_ERR (reported as "warnings" below).
COLLECT_ERR=$(sudo docker exec "$CBS_CONTAINER" timeout --kill-after=30 1200 "$CBCOLLECT_BIN" \
  --log-redaction-level=partial \
  "$OUT_PATH_IN_CONTAINER" 2>&1 >/dev/null)
COLLECT_RC=$?

if [ "$COLLECT_RC" -ne 0 ] || [ ! -s "$OUT_PATH_ON_HOST_REDACTED" ]; then
  # exit 0 here too -- see the comment on the container-not-found branch above.
  jq -nc --arg err "$COLLECT_ERR" --argjson rc "$COLLECT_RC" \
    '{error: "failed to create archive", rc: $rc, stderr: $err}'
  exit 0
fi

# The unredacted copy has served its purpose (cbcollect_info needed it to derive the
# redacted one) and must not linger on disk.
rm -f "$OUT_PATH_ON_HOST"

SIZE=$(stat -c%s "$OUT_PATH_ON_HOST_REDACTED" 2>/dev/null)
jq -nc --arg file "$REDACTED_FILENAME" \
  --argjson size "${SIZE:-0}" \
  --arg warnings "$COLLECT_ERR" \
  '{file: $file, size: $size} + (if $warnings == "" then {} else {warnings: $warnings} end)'
