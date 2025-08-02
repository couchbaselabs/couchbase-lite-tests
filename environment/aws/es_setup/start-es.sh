#!/bin/sh

SSL=${SSL:-true}

SCRIPT=$(readlink -f "$0")
ROOT_DIR=$(dirname "${SCRIPT}")
CONFIG_DIR="${ROOT_DIR}/config"

SG_URL_SCHEME="https"
CONFIG_FILE="es_config.json"
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
echo "Stopping any running edge-server service ..."
sudo systemctl stop couchbase-edge-server
sudo killall couchbase-edge-server

# Start ES in background
echo "Starting edge-server with config: ${BOOTSTRAP_CONFIG_FILE}"
setsid /opt/couchbase-edge-server/bin/couchbase-edge-server "${BOOTSTRAP_CONFIG_FILE}" > /dev/null &

# Wait for it to be ready:
wait_for_uri 200 ${SG_URL_SCHEME}://localhost:59840
status=$(curl -s -k --location -X GET -o /dev/null -w "%{http_code}" ${SG_URL_SCHEME}://localhost:59840/_all_dbs)
if [ "$status" -ge 200 -a "$status" -lt 300 ]; then
   echo "Edge Server is up!"
else
   echo "Edge Server startup failed: ${status}!!"
fi
