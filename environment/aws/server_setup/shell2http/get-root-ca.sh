#!/bin/bash

set -euo pipefail

# Get the CBS cluster certificate via REST API
# This is the root/cluster CA certificate that SGW needs to verify CBS TLS connections

CERT=$(curl -s -k http://localhost:8091/pools/default/certificate 2>/dev/null || true)

if [ -n "$CERT" ] && echo "$CERT" | grep -q "BEGIN CERTIFICATE"; then
    echo "$CERT"
    exit 0
fi

# Fallback: try HTTPS endpoint
CERT=$(curl -s -k https://localhost:18091/pools/default/certificate 2>/dev/null || true)

if [ -n "$CERT" ] && echo "$CERT" | grep -q "BEGIN CERTIFICATE"; then
    echo "$CERT"
    exit 0
fi

echo "ERROR: Could not find CBS root CA certificate"
exit 1

