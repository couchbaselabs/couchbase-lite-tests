#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
REQUEST_BODY=$(read_http_body)

NAME=$(echo "$REQUEST_BODY"     | jq -r '.name')
PASSWORD=$(echo "$REQUEST_BODY" | jq -r '.password')
ROLE=$(echo "$REQUEST_BODY"     | jq -r '.role // ""')
ACCESS=$(echo "$REQUEST_BODY"   | jq -c '.access // empty')

# ------------------------------------------------------------------
# Validate required fields
# ------------------------------------------------------------------
if [[ -z "$NAME" || "$NAME" == "null" || \
      -z "$PASSWORD" || "$PASSWORD" == "null" ]]; then
    echo "name and password are required"
    exit 1
fi

USERS_JSON="$HOME/user/users.json"
EDGE_SERVER_BIN="/opt/couchbase-edge-server/bin/couchbase-edge-server"

# ------------------------------------------------------------------
# Skip CLI creation if user already exists, but still patch access
# if provided (idempotent re-runs update access without recreating).
# ------------------------------------------------------------------
USER_EXISTS=false
if json5 "$USERS_JSON" | jq -e --arg name "$NAME" '.[$name]' > /dev/null 2>&1; then
    echo "User '$NAME' already exists, skipping CLI creation"
    USER_EXISTS=true
fi

if [[ "$USER_EXISTS" == "false" ]]; then
    # Build CLI command — omit --role flag when role is empty/null
    COMMAND=(
        "$EDGE_SERVER_BIN"
        --add-user "$USERS_JSON" "$NAME"
        --create
        --password "$PASSWORD"
    )
    if [[ -n "$ROLE" && "$ROLE" != "null" ]]; then
        COMMAND+=(--role "$ROLE")
    fi

    if ! "${COMMAND[@]}"; then
        echo "Failed to add user '$NAME'"
        exit 1
    fi
fi

# ------------------------------------------------------------------
# Patch the access block if provided.
# jq writes to a temp file then atomically replaces users.json.
# ------------------------------------------------------------------
if [[ -n "$ACCESS" ]]; then
    TMP=$(mktemp)
    if json5 "$USERS_JSON" | \
      jq --arg name "$NAME" \
          --argjson access "$ACCESS" \
          '.[$name].access = $access' > "$TMP"; then \
        mv "$TMP" "$USERS_JSON"
        echo "User '$NAME' added/updated with access block"
    else
        rm -f "$TMP"
        echo "Failed to patch access block for user '$NAME'"
        exit 1
    fi
else
    echo "User '$NAME' added successfully (no access block)"
fi