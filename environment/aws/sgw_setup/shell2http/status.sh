#!/bin/bash

if pgrep -f "sync_gateway" > /dev/null; then
    echo "running"
    exit 0
else
    echo "stopped"
    exit 0
fi
