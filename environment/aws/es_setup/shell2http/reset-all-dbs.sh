#!/bin/bash

# Wipe every Edge Server database and audit log, and restore the provisioned datasets.
# Unlike /reset-db this takes no request body, so it needs no name and no working Edge
# Server.  The Edge Server recreates the audit log its config names on its next start.

set -euo pipefail

DB_DIR="$HOME/database"
AUDIT_DIR="$HOME/audit"

shopt -s nullglob

for db in "$DB_DIR"/*.cblite2; do
  rm -rf "$db"
  echo "Removed $(basename "$db")"
done

for zip in "$DB_DIR"/*.cblite2.zip; do
  unzip -o "$zip" -d "$DB_DIR" >/dev/null
  echo "Restored $(basename "$zip" .zip)"
done

for log in "$AUDIT_DIR"/*; do
  rm -f "$log"
  echo "Removed $(basename "$log")"
done

echo "Databases and audit logs reset"
