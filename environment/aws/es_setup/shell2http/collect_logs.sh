#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
REQUEST_BODY=$(read_http_body)

set -uo pipefail

OUT_DIR="/home/ec2-user/collect"
LOG_DIR="/home/ec2-user/log"
AUDIT_DIR="/home/ec2-user/audit"

FILENAME="es-collect-$(date -u +%Y%m%d-%H%M%S).tar.gz"

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

{
  echo "=== collected $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "=== uname ==="       ; uname -a
  echo "=== es version ==="  ; "$ES_BIN" --version 2>&1
  echo "=== processes ==="   ; ps aux | grep -i [c]ouchbase-edge-server
  echo "=== listeners ==="   ; ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null
  echo "=== disk ==="        ; df -h
  echo "=== memory ==="      ; free -m 2>/dev/null
  echo "=== firewall ==="    ; sudo iptables -L -n 2>/dev/null
  echo "=== dmesg tail ===" ; sudo dmesg 2>/dev/null | tail -100
} > "$STAGE/system/system-info.txt" 2>&1

tar czf "$OUT_DIR/$FILENAME" -C "$STAGE" . 2>/dev/null

if [ -f "$OUT_DIR/$FILENAME" ]; then
  echo "{\"file\":\"collect/$FILENAME\",\"size\":$(stat -c%s "$OUT_DIR/$FILENAME")}"
else
  echo "{\"error\":\"failed to create archive\"}"
  exit 1
fi