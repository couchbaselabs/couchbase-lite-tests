#!/bin/bash

# Wipe every Edge Server database and restore the datasets setup_edge_servers.py
# provisioned. Unlike /reset-db this takes no request body, so it works even when
# Edge Server is stopped or running a config the caller cannot authenticate against.

set -euo pipefail

DB_DIR="$HOME/database"

shopt -s nullglob

for db in "$DB_DIR"/*.cblite2; do
  rm -rf "$db"
  echo "Removed $(basename "$db")"
done

for zip in "$DB_DIR"/*.cblite2.zip; do
  unzip -o "$zip" -d "$DB_DIR" >/dev/null
  echo "Restored $(basename "$zip" .zip)"
done

echo "Databases reset"
