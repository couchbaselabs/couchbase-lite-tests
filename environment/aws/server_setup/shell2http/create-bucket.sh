#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

REQUEST_BODY=$(read_http_body)
BUCKET=$(echo "$REQUEST_BODY" | jq -r '.bucket')
REST_PORT=$(echo "$REQUEST_BODY" | jq -r '.port // 8091')
RAM_QUOTA=$(echo "$REQUEST_BODY" | jq -r '.ram_quota // 100')
USERNAME=$(echo "$REQUEST_BODY" | jq -r '.username // "Administrator"')
PASSWORD=$(echo "$REQUEST_BODY" | jq -r '.password // "password"')

# Create bucket
HTTP_CODE=$(curl -s -o /tmp/bucket_result.txt -w "%{http_code}" \
  -X POST "http://localhost:$REST_PORT/pools/default/buckets" \
  -u "$USERNAME:$PASSWORD" \
  -d "name=$BUCKET&ramQuota=$RAM_QUOTA&bucketType=couchbase")

if [ "$HTTP_CODE" = "400" ] && grep -q "already exists" /tmp/bucket_result.txt; then
  echo "Bucket already exists, continuing..."
elif [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "202" ]; then
  echo "ERROR: Failed to create bucket: HTTP $HTTP_CODE"
  cat /tmp/bucket_result.txt
  exit 1
fi

echo "Waiting for bucket to become reachable..."

for i in {1..30}; do
  BUCKET_STATUS=$(curl -s -o /tmp/bucket_status.txt -w "%{http_code}" \
    "http://localhost:$REST_PORT/pools/default/buckets/$BUCKET" \
    -u "$USERNAME:$PASSWORD")

  if [ "$BUCKET_STATUS" = "200" ]; then
    echo "Bucket '$BUCKET' is reachable"
    exit 0
  fi

  echo "Waiting for bucket to be ready... ($i/30)"
  sleep 2
done

echo "ERROR: Bucket '$BUCKET' did not become reachable within 60 seconds"
exit 1