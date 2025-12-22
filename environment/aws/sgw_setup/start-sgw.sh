#!/bin/sh

SSL=${SSL:-true}

SCRIPT=$(readlink -f "$0")
ROOT_DIR=$(dirname "${SCRIPT}")
CONFIG_DIR="${ROOT_DIR}/config"

SG_URL_SCHEME="https"
CONFIG_FILE="bootstrap.json" 
if [ "${SSL}" = "false" ]; then
  SG_URL_SCHEME="http" 
  CONFIG_FILE="bootstrap-nonssl.json" 
fi
BOOTSTRAP_CONFIG_FILE="${CONFIG_DIR}/${CONFIG_FILE}"

wait_for_uri() {
  expected=$1
  shift
  uri=$1
  echo "Waiting for $uri to be available ..."
  while true; do
    status=$(curl -k -s -w "%{http_code}" -o /dev/null $*)
    if [ "x$status" = "x$expected" ]; then break; fi
    echo "$uri not ready, waiting 5 seconds ..."
    sleep 5
  done
  echo "$uri is ready"
}

# Stop any current SG service:
echo "Stopping any running sync-gateway service ..."
sudo systemctl stop sync_gateway
sudo killall sync_gateway

# Wait for the server to start and settle
wait_for_uri 200 http://10.0.1.23:8093/admin/ping
echo "Giving the server 5 seconds to settle..."
sleep 5

# Start SG in background
echo "Starting sync-gateway with config: ${BOOTSTRAP_CONFIG_FILE}"
nohup /opt/couchbase-sync-gateway/bin/sync_gateway "${BOOTSTRAP_CONFIG_FILE}" &

# Wait for it to be ready:
wait_for_uri 200 ${SG_URL_SCHEME}://localhost:4984
status=$(curl -s -k --location -X GET --user "admin:password" -o /dev/null -w "%{http_code}" ${SG_URL_SCHEME}://localhost:4985/_all_dbs)
if [ "$status" -ge 200 -a "$status" -lt 300 ]; then
   echo "Sync Gateway is up!"
else
   echo "Sync Gateway startup failed: ${status}!!"
fi
