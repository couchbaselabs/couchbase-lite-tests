#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
REQUEST_BODY=$(read_http_body)

NAME=$(echo "$REQUEST_BODY" | jq -r '.name')
PASSWORD=$(echo "$REQUEST_BODY" | jq -r '.password')
ROLE=$(echo "$REQUEST_BODY" | jq -r '.role')

# Validate inputs
if [[ -z "$NAME" || "$NAME" == "null" || \
      -z "$PASSWORD" || "$PASSWORD" == "null" || \
      -z "$ROLE" || "$ROLE" == "null" ]]; then
     echo "name, password, and role are required"
    exit 1
fi

USERS_JSON="$HOME/user/users.json"
EDGE_SERVER_BIN="/opt/couchbase-edge-server/bin/couchbase-edge-server"

# Build command (matches Python implementation)
COMMAND=(
    "$EDGE_SERVER_BIN"
    --add-user "$USERS_JSON" "$NAME"
    --create
    --role "$ROLE"
    --password "$PASSWORD"
)

# Execute
if "${COMMAND[@]}"; then
   echo "User added successfully"
else
    echo "Failed to add user"
    exit 1
fi
