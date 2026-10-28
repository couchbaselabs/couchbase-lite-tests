#!/bin/bash

# Brings the container up the way setup_edge_servers.py brings up an AWS host, then follows
# the Edge Server log so `docker logs` shows it.

set -euo pipefail
cd "$HOME"

for zip in database/*.cblite2.zip; do
  unzip -o -q "$zip" -d database
done

./caddy start --config Caddyfile --adapter caddyfile

# Test configs point Edge Server at Sync Gateway on localhost, which is the host, not this container.
for port in ${HOST_FORWARD_PORTS:-}; do
  socat "TCP-LISTEN:$port,fork,reuseaddr,bind=127.0.0.1" "TCP:host.docker.internal:$port" &
done

bash shell2http/start.sh
echo '{"name":"admin_user","password":"password","role":"admin"}' | bash shell2http/add-user.sh
echo '{}' | bash shell2http/start-edgeserver.sh

exec tail -F log/edge.log
