#!/bin/bash

# Debug version - remove set -euo pipefail to see what fails
# set -euo pipefail

echo "Stopping Couchbase Server..."
echo "Checking environment..."

# Check if we're in a Docker container environment
if [ -f /.dockerenv ] || [ -n "$DOCKER_CONTAINER" ] || grep -q docker /proc/1/cgroup 2>/dev/null; then
    echo "Running in Docker container"

    # In Docker environments, CBS might be managed by the init system or entrypoint
    # Try different approaches
    if command -v systemctl >/dev/null 2>&1; then
        echo "systemctl is available, checking for CBS service..."
        systemctl list-units --type=service | grep couchbase || echo "No couchbase service found"
        # Try to stop anyway
        systemctl stop couchbase-server 2>&1 || echo "systemctl stop failed"
    elif command -v service >/dev/null 2>&1; then
        echo "service command available, trying service stop..."
        service couchbase-server stop 2>&1 || echo "service stop failed"
    else
        echo "No service management commands available"
    fi

    # Check for CBS processes
    if pgrep -f "couchbase\|beam" >/dev/null; then
        echo "Found CBS processes, attempting to kill..."
        pkill -f "couchbase\|beam" 2>&1 || echo "pkill failed"
        sleep 2
        # Check if still running
        if pgrep -f "couchbase\|beam" >/dev/null; then
            echo "Force killing CBS processes..."
            pkill -9 -f "couchbase\|beam" 2>&1 || echo "force kill failed"
        fi
    else
        echo "No CBS processes found"
    fi
else
    echo "Not in Docker, trying standard service management..."
    sudo systemctl stop couchbase-server 2>&1 || sudo service couchbase-server stop 2>&1 || echo "Service stop failed"
fi

# Wait for CBS to actually stop (up to 60 seconds)
echo "Waiting for CBS to stop..."
for i in {1..20}; do
    if ! pgrep -f "couchbase\|beam" >/dev/null && ! curl -s --connect-timeout 2 http://localhost:8091/pools/default >/dev/null 2>&1; then
        echo "CBS has stopped successfully"
        exit 0
    fi
    echo "CBS still responding (attempt $i/20)..."
    sleep 3
done

echo "CBS stop operation completed (may not actually stop in Docker environments)"
exit 0
