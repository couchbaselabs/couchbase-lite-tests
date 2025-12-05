#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

REQUEST_BODY=$(read_http_body)

ALLOW=$(echo $REQUEST_BODY | jq -r '.allow')
DENY=$(echo $REQUEST_BODY | jq -r '.deny')
if [[ ( -z "$ALLOW" || "$ALLOW" == "null" ) && ( -z "$DENY" || "$DENY" == "null" ) ]]; then
  echo "Error: provide 'allow' or 'deny' (at least one)"
  exit 1
fi

echo $ALLOW | jq -r '.[]'