#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
set -uo pipefail

OUT_DIR="/home/ec2-user/collect"
LOG_DIR="/home/ec2-user/log"
AUDIT_DIR="/home/ec2-user/audit"

REQ=$(read_http_body | jq -r '.filename')
FILENAME="${REQ:-es-collect-$(date -u +%Y%m%d-%H%M%S).tar.gz}"
FILENAME=$(basename "$FILENAME")

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

tar czf "$OUT_DIR/$FILENAME" -C "$STAGE" . 2>/dev/null

if [ -f "$OUT_DIR/$FILENAME" ]; then
  echo "{\"file\":\"collect/$FILENAME\",\"size\":$(stat -c%s "$OUT_DIR/$FILENAME")}"
else
  echo "{\"error\":\"failed to create archive\"}"
  exit 1
fi
