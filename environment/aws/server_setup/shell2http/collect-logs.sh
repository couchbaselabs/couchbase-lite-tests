#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
set -uo pipefail

LOG_DIR="/home/ec2-user/log"
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

REDACTED_FILENAME="${FILENAME%.zip}-redacted.zip"
OUT_PATH_ON_HOST_REDACTED="$LOG_DIR/$REDACTED_FILENAME"

# cbcollect_info writes its plain archive first and only derives the redacted copy
# afterwards, so writing either one directly into LOG_DIR -- Caddy's unauthenticated
# document root -- would let a concurrent GET for the caller-supplied filename download the
# plain, unredacted archive mid-collection (or a half-written one, if collection then
# fails). Collect into a directory that lives only inside the container instead -- never
# bind-mounted to the host, never served -- and publish just the finished redacted file into
# LOG_DIR as the last step, once collection has already succeeded.
STAGING_DIR_IN_CONTAINER=$(sudo docker exec "$CBS_CONTAINER" mktemp -d)
if [ -z "$STAGING_DIR_IN_CONTAINER" ]; then
  jq -nc '{error: "failed to create staging directory"}'
  exit 0
fi
cleanup() {
  sudo docker exec "$CBS_CONTAINER" rm -rf "$STAGING_DIR_IN_CONTAINER"
}
trap cleanup EXIT

OUT_PATH_IN_CONTAINER="$STAGING_DIR_IN_CONTAINER/$FILENAME"
STAGED_REDACTED_IN_CONTAINER="$STAGING_DIR_IN_CONTAINER/$REDACTED_FILENAME"

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

if [ "$COLLECT_RC" -ne 0 ] || ! sudo docker exec "$CBS_CONTAINER" test -s "$STAGED_REDACTED_IN_CONTAINER"; then
  # exit 0 here too -- see the comment on the container-not-found branch above.
  jq -nc --arg err "$COLLECT_ERR" --argjson rc "$COLLECT_RC" \
    '{error: "failed to create archive", rc: $rc, stderr: $err}'
  exit 0
fi

# The host outlives the run and nothing else prunes LOG_DIR, so keeping every past archive
# fills the disk. Only prune this endpoint's own naming scheme, right before replacing it --
# LOG_DIR also holds CBS's live logs, so it can't be wiped wholesale the way the Edge Server
# sibling does, and clearing it any earlier would leave nothing downloadable for the whole
# collection window.
rm -f "$LOG_DIR"/cbcollect-*.zip

# Publish only the finished, redacted archive -- the plain copy and anything partially
# written never leave the container's own filesystem.
if ! sudo docker cp "$CBS_CONTAINER:$STAGED_REDACTED_IN_CONTAINER" "$OUT_PATH_ON_HOST_REDACTED"; then
  jq -nc '{error: "failed to publish archive"}'
  exit 0
fi

SIZE=$(stat -c%s "$OUT_PATH_ON_HOST_REDACTED" 2>/dev/null)
jq -nc --arg file "$REDACTED_FILENAME" \
  --argjson size "${SIZE:-0}" \
  --arg warnings "$COLLECT_ERR" \
  '{file: $file, size: $size} + (if $warnings == "" then {} else {warnings: $warnings} end)'
