#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
set -uo pipefail

OUT_DIR="/home/ec2-user/collect"
LOG_DIR="/home/ec2-user/log"
AUDIT_DIR="/home/ec2-user/audit"
EDGE_SERVER_BIN="/opt/couchbase-edge-server/bin/couchbase-edge-server"

REQ=$(read_http_body | jq -r '.filename // empty')
FILENAME="${REQ:-es-collect-$(date -u +%Y%m%d-%H%M%S).tar.gz}"

# Reject path traversal - filename is attacker-controllable in principle
FILENAME=$(basename "$FILENAME")
case "$FILENAME" in
  *.tar.gz) ;;
  *) FILENAME="${FILENAME}.tar.gz" ;;
esac

mkdir -p "$OUT_DIR"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/logs" "$STAGE/audit" "$STAGE/config" "$STAGE/system"

cp -a "$LOG_DIR/." "$STAGE/logs/" 2>/dev/null || true
cp -a "$AUDIT_DIR/." "$STAGE/audit/" 2>/dev/null || true

# The live config, which is whatever the last test installed rather than what the
# repo holds. users.json is deliberately left out: it is a credentials file, and
# this archive is published as a Jenkins build artifact.
cp -a /opt/couchbase-edge-server/etc/config.json "$STAGE/config/" 2>/dev/null || true

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

tar czf "$OUT_DIR/$FILENAME" -C "$STAGE" . 2>/dev/null

if [ -f "$OUT_DIR/$FILENAME" ]; then
  echo "{\"file\":\"collect/$FILENAME\",\"size\":$(stat -c%s "$OUT_DIR/$FILENAME")}"
else
  echo "{\"error\":\"failed to create archive\"}"
  exit 1
fi
