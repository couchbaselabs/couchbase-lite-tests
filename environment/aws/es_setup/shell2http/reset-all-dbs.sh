#!/bin/bash

# Wipe every Edge Server database, restore the provisioned datasets and empty the audit
# log. Unlike /reset-db this takes no request body, so it needs no name and no working
# Edge Server.

set -euo pipefail

DB_DIR="$HOME/database"
AUDIT_LOG="$HOME/audit/EdgeServerAuditLog.txt"

shopt -s nullglob

for db in "$DB_DIR"/*.cblite2; do
  rm -rf "$db"
  echo "Removed $(basename "$db")"
done

for zip in "$DB_DIR"/*.cblite2.zip; do
  unzip -o "$zip" -d "$DB_DIR" >/dev/null
  echo "Restored $(basename "$zip" .zip)"
done

# The caller kills the Edge Server first, so nothing appends after this.
if [[ -f "$AUDIT_LOG" ]]; then
  : >"$AUDIT_LOG"
  echo "Emptied $(basename "$AUDIT_LOG")"
fi

echo "Databases reset"
