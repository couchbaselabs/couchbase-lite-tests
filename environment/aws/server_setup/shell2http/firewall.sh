#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

REQUEST_BODY=$(read_http_body)

ALLOW=$(echo $REQUEST_BODY | jq -r '.allow')
DENY=$(echo $REQUEST_BODY | jq -r '.deny')
if [[ ( -z "$ALLOW" || "$ALLOW" == "null" ) && ( -z "$DENY" || "$DENY" == "null" ) ]]; then
#  echo "Error: provide 'allow' or 'deny' (at least one)"
#  exit 1
iptables -F ES_RULES
exit 0
fi

if ! iptables -L ES_RULES >/dev/null 2>&1; then
  iptables -N ES_RULES
fi
iptables -F ES_RULES


if [[ "$ALLOW" != "null" ]]; then
  echo "$ALLOW" | jq -r '.[]' | while read ip; do
    iptables -A ES_RULES -s "$ip" -j ACCEPT
  done
fi

if [[ "$DENY" != "null" ]]; then
  echo "$DENY" | jq -r '.[]' | while read ip; do
    iptables -A ES_RULES -s "$ip" -j DROP
  done
fi

iptables -C INPUT -j ES_RULES 2>/dev/null || iptables -I INPUT -j ES_RULES
iptables -L ES_RULES --line-numbers