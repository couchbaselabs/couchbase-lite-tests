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
  # Always exit 0 and report failure in the JSON body instead. On a non-zero exit, shell2http (-cgi -500) answers
  # HTTP 500 with this script's stdout followed by "exec error: exit status N", and Shell2HttpClient.call() raises
  # CblRemoteBadResponseError for it, so collect_logs() never gets a JSON body it can parse. This script's stderr
  # never reaches the caller either way: shell2http writes it only to its own log, which start.sh sends to /dev/null.
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

# Bounded: a stuck GSI/indexer service is exactly the case this exists to diagnose, and cbcollect_info has no timeout
# of its own. start.sh runs this script under with-timeout.sh, which stops it at the ?timeout= the client sends
# (_COLLECT_LOGS_TIMEOUT in couchbaseserver.py, the only place the budget is set). That kills the host's `docker exec`
# but not cbcollect_info inside the container, so it gets the same limit there.
CONTAINER_TIMEOUT=()
if [[ "${QUERY_STRING:-}" =~ (^|&)timeout=([0-9]+(\.[0-9]+)?)(&|$) ]]; then
  CONTAINER_TIMEOUT=(timeout --kill-after=1 "${BASH_REMATCH[2]}")
fi
# Only stderr is captured, into COLLECT_ERR; stdout is discarded. cbcollect_info logs every message to stderr,
# including a "<task> - OK" or "Exit code N" line per task -- thousands on a loaded cluster.
COLLECT_ERR=$(sudo docker exec "$CBS_CONTAINER" "${CONTAINER_TIMEOUT[@]}" "$CBCOLLECT_BIN" \
  --log-redaction-level=partial \
  "$OUT_PATH_IN_CONTAINER" 2>&1 >/dev/null)
COLLECT_RC=$?

if [ "$COLLECT_RC" -ne 0 ] || ! sudo docker exec "$CBS_CONTAINER" test -s "$STAGED_REDACTED_IN_CONTAINER"; then
  # Only a failure reports stderr; on success it is progress lines, and the archive has it all as cbcollect_info.log.
  # Linux caps one argv string at 128 KiB: past that, `jq --arg` fails to exec with exit 126 and prints nothing.
  # Keep only the tail: it holds whatever cbcollect_info logged just before exiting, such as a fatal error.
  # exit 0 here too -- see the comment on the container-not-found branch above.
  jq -nc --arg err "$(tail -c 4096 <<<"$COLLECT_ERR")" --argjson rc "$COLLECT_RC" \
    '{error: "failed to create archive", rc: $rc, stderr: $err}'
  exit 0
fi

# The host outlives the run and nothing else prunes LOG_DIR, so keeping every past archive
# fills the disk. Only prune this endpoint's own naming scheme, right before replacing it --
# LOG_DIR also holds CBS's live logs, so it can't be wiped wholesale the way the Edge Server
# sibling does, and clearing it any earlier would leave nothing downloadable for the whole
# collection window.
# Prints {"removed": N, "failed": [names]}, checking each file is really gone afterwards. sudo, since the archives come
# from `sudo docker cp` and the CBS container shares this bind-mounted directory.
prune_old_archives() {
  local archive removed=0 failed=()
  for archive in "$LOG_DIR"/cbcollect-*.zip; do
    [ -e "$archive" ] || continue # no match leaves the pattern itself
    sudo rm -f "$archive"
    if [ -e "$archive" ]; then
      failed+=("$(basename "$archive")")
    else
      removed=$((removed + 1))
    fi
  done
  jq -nc --argjson removed "$removed" '{removed: $removed, failed: $ARGS.positional}' --args "${failed[@]}"
}
PRUNED=$(prune_old_archives)

# Publish only the finished, redacted archive -- the plain copy and anything partially
# written never leave the container's own filesystem.
if ! sudo docker cp "$CBS_CONTAINER:$STAGED_REDACTED_IN_CONTAINER" "$OUT_PATH_ON_HOST_REDACTED"; then
  jq -nc '{error: "failed to publish archive"}'
  exit 0
fi

SIZE=$(stat -c%s "$OUT_PATH_ON_HOST_REDACTED" 2>/dev/null)
jq -nc --arg file "$REDACTED_FILENAME" \
  --argjson size "${SIZE:-0}" \
  --argjson pruned "$PRUNED" \
  '{file: $file, size: $size, pruned: $pruned}'
