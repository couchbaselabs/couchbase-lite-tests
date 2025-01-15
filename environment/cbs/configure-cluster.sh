#!/bin/bash

# Variables
LOGFILE="/var/log/couchbase-setup.log"
CONFIG_DONE_FILE="/var/couchbase-configured"
COUCHBASE_BIN="/opt/couchbase/bin"
ADMIN_USERNAME="Administrator"
ADMIN_PASSWORD="password"
CLUSTER_NAME="vm-cluster"
RAMSIZE=2560
INDEX_RAMSIZE=560
SERVICES="data,index,query"

# Redirect stdout and stderr to the log file
exec 3>&1 1>>${LOGFILE} 2>&1

log() {
  echo "$1" | tee /dev/fd/3
}

config_done() {
  touch ${CONFIG_DONE_FILE}
  log "Couchbase Cluster Setup Completed!"
  log "Admin UI: http://localhost:8091"
  log "Login credentials: ${ADMIN_USERNAME} / ${ADMIN_PASSWORD}"
}

panic() {
  log "Error during configuration. Aborting setup!"
  log "Check logs at: ${LOGFILE}"
  exit 1
}

wait_for_uri() {
  expected=$1
  shift
  uri=$1
  log "Waiting for $uri to be available..."
  while true; do
    status=$(curl -s -w "%{http_code}" -o /dev/null "$@")
    if [ "x$status" = "x$expected" ]; then
      break
    fi
    log "$uri not available yet, retrying in 2 seconds..."
    sleep 2
  done
  log "$uri is ready."
}

couchbase_cli_check() {
  ${COUCHBASE_BIN}/couchbase-cli "$@" || {
    log "Error with couchbase-cli command: $@"
    panic
  }
}

# Main Setup
if [ -e ${CONFIG_DONE_FILE} ]; then
  log "Couchbase cluster already configured. Exiting."
  config_done
  exit 0
fi

log "Starting Couchbase Cluster Setup on VM..."

export PATH=${COUCHBASE_BIN}:${PATH}

# Wait for Couchbase Server to start
wait_for_uri 200 "http://localhost:8091/ui/index.html"

# Initialize cluster
log "Initializing cluster..."
couchbase_cli_check cluster-init \
  -c localhost \
  --cluster-name ${CLUSTER_NAME} \
  --cluster-username ${ADMIN_USERNAME} \
  --cluster-password ${ADMIN_PASSWORD} \
  --services ${SERVICES} \
  --cluster-ramsize ${RAMSIZE} \
  --cluster-index-ramsize ${INDEX_RAMSIZE} \
  --index-storage-setting default

# # Add other nodes to the cluster
# log "Adding nodes to the cluster..."
# for NODE_IP in "192.168.1.101" "192.168.1.102"; do
#   couchbase_cli_check server-add \
#     -c localhost \
#     -u ${ADMIN_USERNAME} \
#     -p ${ADMIN_PASSWORD} \
#     --server-add http://${NODE_IP}:8091 \
#     --server-add-username ${ADMIN_USERNAME} \
#     --server-add-password ${ADMIN_PASSWORD} \
#     --services ${SERVICES}
# done

# # Rebalance the cluster
# log "Rebalancing cluster..."
# couchbase_cli_check rebalance \
#   -c localhost \
#   -u ${ADMIN_USERNAME} \
#   -p ${ADMIN_PASSWORD}

# Create an RBAC admin user
log "Creating RBAC user..."
couchbase_cli_check user-manage --set \
  -c localhost \
  -u ${ADMIN_USERNAME} \
  -p ${ADMIN_PASSWORD} \
  --rbac-username admin \
  --rbac-password password \
  --auth-domain local \
  --roles 'sync_gateway_dev_ops,sync_gateway_configurator[*],mobile_sync_gateway[*],bucket_full_access[*],bucket_admin[*]'

# Finalize
log "Couchbase Cluster Setup Complete!"
config_done
