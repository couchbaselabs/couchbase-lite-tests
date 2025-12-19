#!/bin/bash

echo "Stopping Sync Gateway..."

if ! pgrep -f "sync_gateway" > /dev/null; then
    echo "Sync Gateway is not running"
    exit 0
fi

pkill -f "sync_gateway"

for i in {1..15}; do
    if ! pgrep -f "sync_gateway" > /dev/null; then
        echo "Sync Gateway stopped successfully"
        exit 0
    fi
    sleep 1
done

echo "Force killing Sync Gateway..."
pkill -9 -f "sync_gateway"
echo "Sync Gateway stopped"
