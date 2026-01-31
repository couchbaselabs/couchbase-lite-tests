#!/bin/bash
# Returns raw log file content. No search logic - client does filtering in Python.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

REQUEST_BODY=$(read_http_body)
default_log_file="/home/ec2-user/audit/EdgeServerAuditLog.txt"

log_file=$(echo "$REQUEST_BODY" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('log_file', \"$default_log_file\"))
except Exception:
    print(\"$default_log_file\")
" 2>/dev/null || echo "$default_log_file")

if [[ -f "$log_file" ]]; then
    cat "$log_file" 2>/dev/null || true
fi
