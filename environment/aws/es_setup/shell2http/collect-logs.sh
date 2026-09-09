#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
set -uo pipefail

OUT_DIR="/home/ec2-user/collect"
LOG_DIR="/home/ec2-user/log"
AUDIT_DIR="/home/ec2-user/audit"
CONFIG_FILE="/opt/couchbase-edge-server/etc/config.json"
EDGE_SERVER_BIN="/opt/couchbase-edge-server/bin/couchbase-edge-server"

REQ=$(read_http_body | jq -r '.filename // empty')
FILENAME="${REQ:-es-collect-$(date -u +%Y%m%d-%H%M%S).tar.gz}"

# Reject path traversal - filename is attacker-controllable in principle
FILENAME=$(basename "$FILENAME")
case "$FILENAME" in
  *.tar.gz) ;;
  *) FILENAME="${FILENAME}.tar.gz" ;;
esac

# Only the archive this run makes is kept. The host outlives the run, and nothing else
# prunes this directory, so keeping them all fills the disk.
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/logs" "$STAGE/audit" "$STAGE/config" "$STAGE/system"
MANIFEST="$STAGE/system/collect.log"

# Record what reached the archive, so an empty directory in it is never mistaken for an
# Edge Server that logged nothing.
copy_into() {
  local src=$1 dest=$2
  if [ ! -d "$src" ]; then
    echo "$src: missing, nothing copied" >>"$MANIFEST"
    return
  fi
  cp -a "$src/." "$dest/" 2>>"$MANIFEST"
  echo "$src: $(find "$dest" -type f | wc -l) file(s) copied" >>"$MANIFEST"
}

copy_into "$LOG_DIR" "$STAGE/logs"
copy_into "$AUDIT_DIR" "$STAGE/audit"

# The live config, which is whatever the last test installed rather than what the
# repo holds. users.json is deliberately left out: it is a credentials file, and
# this archive is published as a Jenkins build artifact.
if [ -f "$CONFIG_FILE" ]; then
  cp -a "$CONFIG_FILE" "$STAGE/config/" 2>>"$MANIFEST"
  echo "$CONFIG_FILE: copied" >>"$MANIFEST"
else
  echo "$CONFIG_FILE: missing, nothing copied" >>"$MANIFEST"
fi

# ES_RULES is the valuable one here -- a DROP rule left behind by a chaos test is
# invisible from the logs alone.
{
  echo "=== version ==="
  "$EDGE_SERVER_BIN" --version
  echo
  echo "=== uname ==="
  uname -a
  echo
  echo "=== disk ==="
  df -h
  echo
  echo "=== memory ==="
  free -m
  echo
  echo "=== edge-server processes ==="
  ps -eo pid,etime,rss,cmd | grep '[e]dge-server'
  echo
  echo "=== listening ports ==="
  sudo ss -ltnp
  echo
  echo "=== firewall (ES_RULES) ==="
  sudo iptables -L ES_RULES -n --line-numbers
} >"$STAGE/system/info.txt" 2>&1

TAR_ERR=$(tar czf "$OUT_DIR/$FILENAME" -C "$STAGE" . 2>&1)
TAR_RC=$?

# tar exit 1 means it skipped or could not fully read something, which still leaves
# a usable bundle. Exit 2 and above is fatal, and so is a zero byte archive.
if [ "$TAR_RC" -ge 2 ] || [ ! -s "$OUT_DIR/$FILENAME" ]; then
  rm -f "$OUT_DIR/$FILENAME"
  jq -nc --arg err "$TAR_ERR" --argjson rc "$TAR_RC" \
    '{error: "failed to create archive", rc: $rc, stderr: $err}'
  exit 1
fi

# A size jq can always parse: --argjson rejects the empty string a failed stat leaves,
# which would turn a good archive into a 500.
SIZE=$(stat -c%s "$OUT_DIR/$FILENAME" 2>/dev/null)
jq -nc --arg file "collect/$FILENAME" \
  --argjson size "${SIZE:-0}" \
  --arg warnings "$([ "$TAR_RC" -eq 0 ] || echo "$TAR_ERR")" \
  '{file: $file, size: $size} + (if $warnings == "" then {} else {warnings: $warnings} end)'
