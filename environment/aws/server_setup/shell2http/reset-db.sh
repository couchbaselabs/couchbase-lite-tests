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
  exit 0
fi

rm -rf "$DB_FILENAME"