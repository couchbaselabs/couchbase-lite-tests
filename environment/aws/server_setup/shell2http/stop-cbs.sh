#!/bin/bash
set -euo pipefail

echo "Stopping CBS..."

CBS_CONTAINER=$(sudo docker ps --format '{{.Names}}' | grep -E 'cbs|couchbase' | head -1)
if [ -z "$CBS_CONTAINER" ]; then
    echo "CBS container not running"
    exit 0
fi

sudo docker exec "$CBS_CONTAINER" sv stop /etc/service/couchbase-server
echo "CBS stopped"