#!/bin/bash

echo "Stopping Sync Gateway..."

# Stop the systemd service if running
sudo systemctl stop sync_gateway 2>/dev/null

# Kill any remaining sync_gateway processes
PID=$(pgrep -f "sync_gateway")
if [[ -n "$PID" ]]; then
    echo "Killing sync_gateway process(es): $PID"
    sudo kill -SIGTERM $PID 2>/dev/null
    sleep 2
    # Force kill if still running
    if pgrep -f "sync_gateway" > /dev/null; then
        sudo kill -SIGKILL $(pgrep -f "sync_gateway") 2>/dev/null
    fi
fi

# Verify stopped
if pgrep -f "sync_gateway" > /dev/null; then
    echo "ERROR: Sync Gateway still running"
    exit 1
else
    echo "Sync Gateway stopped successfully"
fi

