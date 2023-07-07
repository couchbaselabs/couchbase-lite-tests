#!/bin/sh

if [ "$#" -lt 1 ]; then
  echo "Usage: start.sh <SSL: true | false>" >&2
  exit 1
fi
SSL=$1

SG_URL_SCHEME="https"
BOOTSTRAP_CONFIG_FILE="bootstrap.json" 
if [ "${SSL}" = "false" ]; then
  SG_URL_SCHEME="http" 
  BOOTSTRAP_CONFIG_FILE="bootstrap-nonssl.json" 
fi

SCRIPT=$(readlink -f "$0")
SCRIPT_DIR=$(dirname "${SCRIPT}")
CONFIG_BASE_DIR=$SCRIPT_DIR/../config

wait_for_uri() {
  expected=$1
  shift
  uri=$1
  echo "Waiting for $uri to be available ..."
  while true; do
    status=$(curl -k -s -w "%{http_code}" -o /dev/null $*)
    if [ "x$status" = "x$expected" ]; then
      break
    fi
    echo "$uri not up yet, waiting 5 seconds ..."
    sleep 5
  done
  echo "$uri is ready ..."
}

sgw_cmd() {
   method=$1
   shift
   endpt=$1
   shift
   data=$1
   curl -k --silent --location --request $method ${SG_URL_SCHEME}://localhost:4985/${endpt}/ \
     --user "admin:password" \
     --header "Content-Type: application/json" \
     --data @"${data}"
}

# Stop any current SG service:
echo "Stop running sync-gateway service ..."
systemctl stop sync_gateway

# Wait for the server to start and settle
wait_for_uri 200 http://cbl-test-cbs:8091/pools/default/buckets/posts -u admin:password
echo "Sleeping for 10 seconds to give server time to settle..."
sleep 10

# Start SG in background
BOOTSTRAP_CONFIG=${CONFIG_BASE_DIR}/${BOOTSTRAP_CONFIG_FILE}
echo "Start sync-gateway with config: ${BOOTSTRAP_CONFIG}"
nohup /opt/couchbase-sync-gateway/bin/sync_gateway "${BOOTSTRAP_CONFIG}" &

# Wait for it to be ready:
echo "Wait for sync-gateway to be ready ..."
sleep 10
wait_for_uri 200 ${SG_URL_SCHEME}://localhost:4984

# Configure travel database:
echo "Configuring travel database"
sgw_cmd PUT travel "${CONFIG_BASE_DIR}/travel-config.json"
sgw_cmd POST travel/_user "${CONFIG_BASE_DIR}/travel-users.json"

# Configure names database:
SG_CONFIG=${CONFIG_BASE_DIR}/names-config.json
echo "Configuring names database"
sgw_cmd PUT names "${CONFIG_BASE_DIR}/names-config.json"
sgw_cmd POST names/_user "${CONFIG_BASE_DIR}/names-users.json"

# Configure posts database:
echo "Configuring posts database"
sgw_cmd PUT posts "${CONFIG_BASE_DIR}/posts-config.json"
sgw_cmd POST posts/_user "${CONFIG_BASE_DIR}/posts-users.json"

echo "Sync Gateway configuration complete!"

# Keep the container alive
tail -f /dev/null
