#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

REQUEST_BODY=$(read_http_body)
default_log_file="/home/ec2-user/audit/EdgeServerAuditLog.txt"

search_string=$(echo "$REQUEST_BODY" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('search_string', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")

log_file=$(echo "$REQUEST_BODY" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('log_file', \"$default_log_file\"))
except Exception:
    print(\"$default_log_file\")
" 2>/dev/null || echo "$default_log_file")

if [[ -z "$search_string" ]]; then
    exit 0
fi

if [[ -f "$log_file" ]]; then
    grep "$search_string" "$log_file" 2>/dev/null || true
fi
