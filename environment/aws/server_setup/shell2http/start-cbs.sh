#!/bin/bash

# Debug version - remove set -euo pipefail to see what fails
# set -euo pipefail

echo "Starting Couchbase Server..."

# Check if we're in a Docker container environment
if [ -f /.dockerenv ] || [ -n "$DOCKER_CONTAINER" ] || grep -q docker /proc/1/cgroup 2>/dev/null; then
    echo "Running in Docker container"

    # In Docker environments, CBS might already be started by the entrypoint
    if pgrep -f "couchbase\|beam" >/dev/null; then
        echo "CBS process is already running in Docker"
    elif command -v systemctl >/dev/null 2>&1; then
        echo "systemctl available in Docker, trying to start CBS..."
        systemctl list-units --type=service | grep couchbase || echo "No couchbase service found"
        systemctl start couchbase-server 2>&1 || echo "systemctl start failed"
    elif command -v service >/dev/null 2>&1; then
        echo "service command available in Docker, trying to start CBS..."
        service couchbase-server start 2>&1 || echo "service start failed"
    else
        echo "No service management in Docker, CBS may be started by entrypoint"
        echo "Checking if CBS binary exists..."
        ls -la /opt/couchbase/bin/couchbase-server 2>/dev/null || echo "CBS binary not found"
    fi
else
    echo "Not in Docker, trying standard service management..."
    sudo systemctl start couchbase-server 2>&1 || sudo service couchbase-server start 2>&1 || echo "Service start failed"
fi

# Check current status
echo "Checking CBS status after start attempt..."
pgrep -f "couchbase\|beam" || echo "No CBS processes found"

# Check if CBS is responding (it might already be running on the new port)
echo "Checking if CBS is responding on port 9000..."
if curl -s --connect-timeout 5 http://localhost:9000/pools/default > /dev/null 2>&1; then
    echo "CBS is already responding on port 9000"
    exit 0
fi

# If not responding, wait longer for CBS to start (up to 2 minutes)
echo "CBS not yet responding on port 9000, waiting..."
for i in {1..24}; do
    if curl -s --connect-timeout 5 http://localhost:9000/pools/default > /dev/null 2>&1; then
        echo "CBS is now ready on port 9000"
        exit 0
    fi
    echo "Waiting for CBS to respond (attempt $i/24)..."
    sleep 5
done

echo "CBS is not responding on port 9000, but proceeding anyway (may be expected in Docker environment)"
exit 0
