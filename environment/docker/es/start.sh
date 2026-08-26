#!/bin/bash
set -e

export HOME=/home/ec2-user
USERS_JSON="$HOME/user/users.json"
ES_BIN="/opt/couchbase-edge-server/bin/couchbase-edge-server"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$HOME/database" "$HOME/cert" "$HOME/user" "$HOME/log" /opt/couchbase-edge-server/etc

ensure_user() {
  local name="$1"
  local password="$2"
  if ! jq -e --arg n "$name" '.[$n]' "$USERS_JSON" >/dev/null 2>&1; then
    echo "Creating user $name"
    "$ES_BIN" --add-user "$USERS_JSON" "$name" --create --role admin --password "$password" || true
  fi
}
ensure_user admin_user password
ensure_user user1 pass
ensure_user user2 pass
ensure_user user3 pass

cp /opt/es-default/config.json /opt/couchbase-edge-server/etc/config.json

shell2http -no-index -cgi -500 -port 20001 \
  /add-user "$SCRIPT_DIR/add-user.sh" \
  /kill-edgeserver "$SCRIPT_DIR/kill-edgeserver.sh" \
  /reset-db "$SCRIPT_DIR/reset-db.sh" \
  /start-edgeserver "$SCRIPT_DIR/start-edgeserver.sh" \
  /write-file "$SCRIPT_DIR/write-file.sh" &

"$ES_BIN" /opt/couchbase-edge-server/etc/config.json > "$HOME/log/edge.log" 2>&1 &

echo "Edge Server and shell2http are up"
tail -f /dev/null
