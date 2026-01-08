#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Read body: first line is cert name, rest is cert content
BODY=$(read_http_body)
CERT_NAME=$(echo "$BODY" | head -n 1)
CERT_CONTENT=$(echo "$BODY" | tail -n +2)

# Use default if name is empty
CERT_NAME="${CERT_NAME:-uploaded-cert.pem}"

# Create cert directory if it doesn't exist
CERT_DIR="/home/ec2-user/cert"
mkdir -p "$CERT_DIR"

# Write certificate to file
CERT_PATH="$CERT_DIR/$CERT_NAME"
echo "$CERT_CONTENT" > "$CERT_PATH"

# Set appropriate permissions
chmod 644 "$CERT_PATH"

echo "Certificate uploaded successfully to: $CERT_PATH"