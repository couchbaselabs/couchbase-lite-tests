#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
REQUEST_BODY=$(read_http_body)

DB_FILENAME=$(echo $REQUEST_BODY | jq -r '.filename')
if [ -z "$DB_FILENAME" ] || [ "$DB_FILENAME" == "null" ]; then
  echo "Error: 'filename' field is required in the request body"
  exit 1
fi

# Ensure it ends with 'cblite2'
if [[ "$DB_FILENAME" != *.cblite2 ]]; then
  echo "Error: 'filename' must end with '.cblite2'"
  exit 1
fi

if [ ! -d "$DB_FILENAME" ]; then
  echo "Database file '$DB_FILENAME' does not exist"
else
  rm -rf "$DB_FILENAME"
fi
ZIP_FILE="${DB_FILENAME}.zip"

if [ -f "$ZIP_FILE" ]; then
  echo "Found zip: $ZIP_FILE"
  unzip -o "$ZIP_FILE" -d "$(dirname "$DB_FILENAME")" >/dev/null 2>&1
else
  echo "Zip file not found: $ZIP_FILE. Nothing to restore."
fi
