#!/bin/bash

# Writes content to a file on the Edge Server host.
# Expects JSON body: {"path": "/some/path", "content": "file content"}
# With "encoding": "base64", content is decoded first, so binary files (e.g. DER) survive.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
REQUEST_BODY=$(read_http_body)

PATH_VALUE=$(echo "$REQUEST_BODY" | jq -r '.path')
CONTENT=$(echo "$REQUEST_BODY" | jq -r '.content')
ENCODING=$(echo "$REQUEST_BODY" | jq -r '.encoding // "text"')

if [[ -z "$PATH_VALUE" || "$PATH_VALUE" == "null" ]]; then
  echo "Error: 'path' field is required in the request body"
  exit 1
fi

if [[ -z "$CONTENT" || "$CONTENT" == "null" ]]; then
  echo "Error: 'content' field is required in the request body"
  exit 1
fi

mkdir -p "$(dirname "$PATH_VALUE")"
case "$ENCODING" in
  text)
    printf '%s' "$CONTENT" >"$PATH_VALUE"
    ;;
  base64)
    # A shell variable cannot hold a NUL byte, so decode straight into the file.
    if ! printf '%s' "$CONTENT" | base64 -d >"$PATH_VALUE"; then
      echo "Error: 'content' is not valid base64"
      exit 1
    fi
    ;;
  *)
    echo "Error: unknown encoding '$ENCODING' (expected 'text' or 'base64')"
    exit 1
    ;;
esac
echo '{"ok": true}'
