#!/bin/bash

# Wipe every Edge Server database and restore the datasets the AWS setup
# provisioned, so the next test starts from the state setup_edge_servers.py
# left behind.
#
# Unlike /reset-db this needs no request body and no knowledge of which
# databases a test created, so it works even when Edge Server is stopped or
# running a config the caller cannot authenticate against.

DB_DIR="$HOME/database"

shopt -s nullglob

for db in "$DB_DIR"/*.cblite2; do
  rm -rf "$db"
  echo "Removed $(basename "$db")"
done

for zip in "$DB_DIR"/*.cblite2.zip; do
  unzip -o "$zip" -d "$DB_DIR" >/dev/null 2>&1
  echo "Restored $(basename "$zip" .zip)"
done

echo "Databases reset"
