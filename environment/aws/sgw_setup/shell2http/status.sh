#!/bin/bash

echo "=== Sync Gateway Status ==="

# Check if process is running
PID=$(pgrep -f "sync_gateway")
if [[ -n "$PID" ]]; then
    echo "Process: Running (PID: $PID)"
else
    echo "Process: Stopped"
    exit 0
fi

# Check if API is responding
if curl -sk --connect-timeout 2 https://localhost:4984/ > /dev/null 2>&1; then
    echo "Public API (4984): Responding"
else
    echo "Public API (4984): Not responding"
fi

if curl -sk --connect-timeout 2 -u admin:password https://localhost:4985/ > /dev/null 2>&1; then
    echo "Admin API (4985): Responding"
else
    echo "Admin API (4985): Not responding"
fi

