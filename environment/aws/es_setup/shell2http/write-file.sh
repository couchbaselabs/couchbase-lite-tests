#!/bin/bash

# Writes content to a file on the Edge Server host.
# Expects JSON body: {"path": "/some/path", "content": "file content"}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
REQUEST_BODY=$(read_http_body)

PATH_VALUE=$(echo "$REQUEST_BODY" | jq -r '.path')
CONTENT=$(echo "$REQUEST_BODY" | jq -r '.content')

if [[ -z "$PATH_VALUE" || "$PATH_VALUE" == "null" ]]; then
  echo "Error: 'path' field is required in the request body"
  exit 1
fi

if [[ -z "$CONTENT" || "$CONTENT" == "null" ]]; then
  echo "Error: 'content' field is required in the request body"
  exit 1
fi

mkdir -p "$(dirname "$PATH_VALUE")"
printf '%s' "$CONTENT" > "$PATH_VALUE"
echo '{"ok": true}'

