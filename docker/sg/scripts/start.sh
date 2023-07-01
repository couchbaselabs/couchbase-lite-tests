#!/bin/sh

if [ "$#" -lt 1 ]; then
  echo "Usage: start.sh <SSL: true | false>" >&2
  exit 1
fi

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

SSL=$1
SCRIPT=$(readlink -f "$0")
SCRIPT_DIR=$(dirname "${SCRIPT}")
CONFIG_BASE_DIR=$SCRIPT_DIR/../config

SG_URL_SCHEME="https"
BOOTSTRAP_CONFIG_FILE="bootstrap.json" 
if [ "${SSL}" = "false" ]; then
  SG_URL_SCHEME="http" 
  BOOTSTRAP_CONFIG_FILE="bootstrap-nonssl.json" 
fi

# Stop current SG service:
echo "Stop running sync-gateway service ..."
systemctl stop sync_gateway

wait_for_uri 200 http://cbl-test-cbs:8091/pools/default/buckets/posts -u admin:password
echo "Sleeping for 10 seconds to give server time to settle..."
sleep 10

# Start SG in background:
BOOTSTRAP_CONFIG=${CONFIG_BASE_DIR}/${BOOTSTRAP_CONFIG_FILE}
echo "Start sync-gateway with config : ${BOOTSTRAP_CONFIG} ..."

nohup /opt/couchbase-sync-gateway/bin/sync_gateway "${BOOTSTRAP_CONFIG}" &

# Wait for SG to be ready:
echo "Wait for sync-gateway to be ready ..."
sleep 10
wait_for_uri 200 ${SG_URL_SCHEME}://localhost:4984

# Configure travel database:
SG_CONFIG=${CONFIG_BASE_DIR}/travel-config.json
echo "Configure travel database : ${SG_CONFIG}"
curl -k --silent --location --request PUT ${SG_URL_SCHEME}://localhost:4985/travel/ \
--user "admin:password" \
--header "Content-Type: application/json" \
--data @"${SG_CONFIG}"

echo "Configure users for travel database"
curl -k --silent --location --request POST ${SG_URL_SCHEME}://localhost:4985/travel/_user/ \
  --user "admin:password" \
  --header "Content-Type: application/json" \
  --data "{
      \"name\": \"user1\",
      \"password\": \"pass\",
      \"collection_access\": {
          \"travel\": {
              \"airlines\": {\"admin_channels\": [\"*\"]},
              \"routes\": {\"admin_channels\": [\"*\"]},
              \"airports\": {\"admin_channels\": [\"*\"]},
              \"landmarks\": {\"admin_channels\": [\"*\"]},
              \"hotels\": {\"admin_channels\": [\"*\"]}
          }
      }
  }"

# Configure names database:
SG_CONFIG=${CONFIG_BASE_DIR}/names-config.json
echo "Configure names database : ${SG_CONFIG}"
curl -k --silent --location --request PUT ${SG_URL_SCHEME}://localhost:4985/names/ \
--user "admin:password" \
--header "Content-Type: application/json" \
--data @"${SG_CONFIG}"

echo "Configure users for names database"
curl -k --silent --location --request POST ${SG_URL_SCHEME}://localhost:4985/names/_user/ \
  --user "admin:password" \
  --header "Content-Type: application/json" \
  --data "{
      \"name\": \"user1\",
      \"password\": \"pass\",
      \"collection_access\": {
          \"_default\": {
              \"_default\": {\"admin_channels\": [\"*\"]}
          }
      }
  }"

# Configure posts database:
SG_CONFIG=${CONFIG_BASE_DIR}/posts-config.json
echo "Configure posts database : ${SG_CONFIG}"
curl -k --silent --location --request PUT ${SG_URL_SCHEME}://localhost:4985/posts/ \
--user "admin:password" \
--header "Content-Type: application/json" \
--data @"${SG_CONFIG}"

echo "Configure users for names database"
curl -k --silent --location --request POST ${SG_URL_SCHEME}://localhost:4985/posts/_user/ \
  --user "admin:password" \
  --header "Content-Type: application/json" \
  --data "{
      \"name\": \"user1\",
      \"password\": \"pass\",
      \"collection_access\": {
          \"_default\": {
              \"posts\": {\"admin_channels\": [\"group1\", \"group2\"]}
          }
      }
  }"

echo "Configuration completed!"

# Keep the container alive
tail -f /dev/null
