#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Restarting Sync Gateway..."

# Parse config from QUERY_STRING (shell2http sets this, not HTTP_config)
# QUERY_STRING format: config=value or config=value&other=...
if [[ "$QUERY_STRING" =~ config=([^&]*) ]]; then
    CONFIG_VALUE="${BASH_REMATCH[1]}"
else
    CONFIG_VALUE="bootstrap"
fi

echo "DEBUG: QUERY_STRING=${QUERY_STRING:-<not set>}"
echo "DEBUG: Parsed config: ${CONFIG_VALUE}"

bash "$SCRIPT_DIR/stop-sgw.sh"
sleep 2

# Export for start-sgw.sh
export HTTP_config="$CONFIG_VALUE"
bash "$SCRIPT_DIR/start-sgw.sh"
