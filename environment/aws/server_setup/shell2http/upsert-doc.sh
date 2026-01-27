#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

REQUEST_BODY=$(read_http_body)
BUCKET=$(echo "$REQUEST_BODY" | jq -r '.bucket')
DOC_ID=$(echo "$REQUEST_BODY" | jq -r '.doc_id')
DOC_BODY=$(echo "$REQUEST_BODY" | jq -c '.doc_body')

# Use query_port if provided; fallback to 8093
QUERY_PORT=$(echo "$REQUEST_BODY" | jq -r '.query_port // 8093')
USERNAME=$(echo "$REQUEST_BODY" | jq -r '.username // "Administrator"')
PASSWORD=$(echo "$REQUEST_BODY" | jq -r '.password // "password"')

echo "Inserting document $DOC_ID into bucket $BUCKET on query port $QUERY_PORT..."

QUERY="UPSERT INTO \`$BUCKET\` (KEY, VALUE) VALUES (\"$DOC_ID\", $DOC_BODY)"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "http://localhost:$QUERY_PORT/query/service" \
    -u "$USERNAME:$PASSWORD" \
    -d "statement=$QUERY")

if [ "$HTTP_CODE" = "200" ]; then
    echo "Document inserted successfully"
    exit 0
fi

echo "ERROR: Failed to insert document: HTTP $HTTP_CODE"
exit 1