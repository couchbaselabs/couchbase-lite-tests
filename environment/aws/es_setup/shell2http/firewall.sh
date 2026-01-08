#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

REQUEST_BODY=$(read_http_body)

ALLOW=$(echo $REQUEST_BODY | jq -r '.allow')
DENY=$(echo $REQUEST_BODY | jq -r '.deny')
if [[ ( -z "$ALLOW" || "$ALLOW" == "null" ) && ( -z "$DENY" || "$DENY" == "null" ) ]]; then
#  echo "Error: provide 'allow' or 'deny' (at least one)"
#  exit 1
sudo iptables -F ES_RULES
exit 0
fi

if ! sudo iptables -L ES_RULES >/dev/null 2>&1; then
  sudo iptables -N ES_RULES
fi
sudo iptables -F ES_RULES


if [[ "$ALLOW" != "null" ]]; then
  echo "$ALLOW" | jq -r '.[]' | while read ip; do
    sudo iptables -A ES_RULES -s "$ip" -j ACCEPT
  done
fi

if [[ "$DENY" != "null" ]]; then
  echo "$DENY" | jq -r '.[]' | while read ip; do
    sudo iptables -A ES_RULES -s "$ip" -j DROP
  done
fi
sudo iptables -C INPUT -p tcp --dport 22 -j ACCEPT  || sudo iptables -I INPUT 1 -p tcp --dport 22 -j ACCEPT
sudo iptables -D INPUT -j ES_RULES 2>/dev/null
sudo iptables -I INPUT 2 -j ES_RULES
sudo iptables -L ES_RULES --line-numbers