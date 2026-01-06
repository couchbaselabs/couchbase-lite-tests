#!/bin/bash

# Debug version - remove set -euo pipefail to see what fails
# set -euo pipefail

# Configure CBS ports by modifying static_config and restarting
# Usage: configure-cbs-ports.sh <rest_port> <ssl_port> <memcached_port> <memcached_ssl_port>

REST_PORT="${rest_port:-9000}"
SSL_PORT="${ssl_port:-1900}"
MEMCACHED_PORT="${memcached_port:-9050}"
MEMCACHED_SSL_PORT="${memcached_ssl_port:-9057}"

echo "Configuring CBS with ports: REST=$REST_PORT, SSL=$SSL_PORT, MEMCACHED=$MEMCACHED_PORT, MEMCACHED_SSL=$MEMCACHED_SSL_PORT"
echo "Current user: $(whoami)"
echo "Working directory: $(pwd)"

# Check if static_config file exists
STATIC_CONFIG="/opt/couchbase/etc/couchbase/static_config"
echo "Looking for static_config at: $STATIC_CONFIG"
if [ ! -f "$STATIC_CONFIG" ]; then
    echo "WARNING: static_config file does not exist at $STATIC_CONFIG"
    echo "Checking alternative locations..."
    find /opt/couchbase -name "*static*" -type f 2>/dev/null || echo "No static config files found"
    echo "Creating static_config file..."
    mkdir -p /opt/couchbase/etc/couchbase
    touch "$STATIC_CONFIG"
    ls -la /opt/couchbase/etc/couchbase/ || echo "Directory listing failed"
else
    echo "static_config file found"
fi

echo "static_config file exists, checking permissions:"
ls -la "$STATIC_CONFIG"

# Check if we can read the file
echo "Current content of static_config:"
cat "$STATIC_CONFIG" || echo "Failed to read static_config"

# Backup current config
echo "Backing up current config..."
cp "$STATIC_CONFIG" "${STATIC_CONFIG}.bak" 2>/dev/null || echo "Backup failed, continuing..."
cp /opt/couchbase/var/lib/couchbase/config/config.dat /opt/couchbase/var/lib/couchbase/config/config.dat.bak 2>/dev/null || echo "config.dat backup failed, continuing..."

# Show current config before changes
echo "=== STATIC_CONFIG BEFORE CHANGES ==="
cat "$STATIC_CONFIG" || echo "Failed to read static_config"
echo "=== END BEFORE ==="

# Remove old port entries if they exist
echo "Removing old port entries..."
sed -i '/{rest_port,/d' "$STATIC_CONFIG" && echo "Removed rest_port entries" || echo "Failed to remove rest_port entries"
sed -i '/{memcached_port,/d' "$STATIC_CONFIG" && echo "Removed memcached_port entries" || echo "Failed to remove memcached_port entries"
sed -i '/{ssl_rest_port,/d' "$STATIC_CONFIG" && echo "Removed ssl_rest_port entries" || echo "Failed to remove ssl_rest_port entries"
sed -i '/{memcached_ssl_port,/d' "$STATIC_CONFIG" && echo "Removed memcached_ssl_port entries" || echo "Failed to remove memcached_ssl_port entries"

echo "=== STATIC_CONFIG AFTER REMOVING OLD ENTRIES ==="
cat "$STATIC_CONFIG" || echo "Failed to read static_config after modifications"
echo "=== END AFTER REMOVAL ==="

# Add new port entries
echo "Adding new port entries..."
echo "{rest_port, $REST_PORT}." >> "$STATIC_CONFIG"
echo "{memcached_port, $MEMCACHED_PORT}." >> "$STATIC_CONFIG"
echo "{ssl_rest_port, $SSL_PORT}." >> "$STATIC_CONFIG"
echo "{memcached_ssl_port, $MEMCACHED_SSL_PORT}." >> "$STATIC_CONFIG"

echo "Final content of static_config:"
cat "$STATIC_CONFIG" || echo "Failed to read final static_config"

# Remove config.dat to force cluster recreation
echo "Removing config.dat..."
rm -rf /opt/couchbase/var/lib/couchbase/config/config.dat || echo "Failed to remove config.dat"
rm -rf /opt/couchbase/var/lib/couchbase/config/chronicle/* || echo "Failed to remove chronicle files"

echo "=== STATIC_CONFIG AFTER ADDING NEW ENTRIES ==="
cat "$STATIC_CONFIG" || echo "Failed to read final static_config"
echo "=== END FINAL CONFIG ==="

echo "Configuration updated. CBS restart required for changes to take effect."
echo "Script completed successfully"
