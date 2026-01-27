#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Read config from JSON body
REQUEST_BODY=$(read_http_body)
HOSTNAME=$(echo "$REQUEST_BODY" | jq -r '.hostname // "localhost"')
REST_PORT=$(echo "$REQUEST_BODY" | jq -r '.rest_port // 8091')
SSL_PORT=$(echo "$REQUEST_BODY" | jq -r '.ssl_port // 18091')
MEMCACHED_PORT=$(echo "$REQUEST_BODY" | jq -r '.memcached_port // 11210')
MEMCACHED_SSL_PORT=$(echo "$REQUEST_BODY" | jq -r '.memcached_ssl_port // 11207')

echo "Configuring CBS ports\nREST=$REST_PORT, SSL=$SSL_PORT, MEMCACHED=$MEMCACHED_PORT, MEMCACHED_SSL=$MEMCACHED_SSL_PORT"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -u Administrator:password -X PUT \
  "http://localhost:8091/node/controller/setupAlternateAddresses/external" \
  -d "hostname=$HOSTNAME" \
  -d "kv=$MEMCACHED_PORT" \
  -d "kvSSL=$MEMCACHED_SSL_PORT" \
  -d "mgmt=$REST_PORT" \
  -d "mgmtSSL=$SSL_PORT"
)

if [ "$HTTP_CODE" != "200" ]; then
    echo "ERROR: Failed to configure alternate ports: HTTP: $HTTP_CODE"
    exit 1
fi

echo "Alternate ports configured successfully"

# Setup iptables port forwarding for alternate ports
echo "Setting up iptables forwarding..."

# Since Host Mode means the container uses the host IP, we forward to 127.0.0.1
add_forward_socat() {
    local EXTERNAL_PORT=$1
    local INTERNAL_PORT=$2

    echo "Forwarding port $EXTERNAL_PORT -> $INTERNAL_PORT via socat"
    
    # Check if socat is already running for this port to avoid duplicates
    if ! pgrep -f "TCP-LISTEN:$EXTERNAL_PORT" > /dev/null; then
        # Run socat in the background. 'fork' allows multiple simultaneous connections.
        # 'reuseaddr' allows the script to restart without "address already in use" errors.
        nohup socat TCP-LISTEN:"$EXTERNAL_PORT",fork,reuseaddr TCP:127.0.0.1:"$INTERNAL_PORT" > /dev/null 2>&1 &
    else
        echo "Socat forwarder for port $EXTERNAL_PORT already exists."
    fi
}

# Apply to your ports
add_forward_socat "$REST_PORT" 8091
add_forward_socat "$SSL_PORT" 18091
add_forward_socat "$MEMCACHED_PORT" 11210
add_forward_socat "$MEMCACHED_SSL_PORT" 11207

echo "Port forwarding complete. Alternate ports should now be reachable externally."
exit 0