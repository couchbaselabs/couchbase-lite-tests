#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
    echo "Usage: $0 <cbl_version> <sgw_from> <sgw_to> [--setup-only]"
    echo "  <cbl_version>: The Couchbase Lite version to test against."
    echo "  <sgw_from>:    The starting Sync Gateway version (all 3 nodes)."
    echo "  <sgw_to>:      The target Sync Gateway version to roll each node to."
    echo "  --setup-only:  Build test server and setup backend only; skip pytest."
    echo "  Build numbers are auto-fetched from proget."
    exit 1
}

if [ "$#" -lt 3 ]; then usage; fi

CBL_VERSION="$1"
SGW_FROM="$2"
SGW_TO="$3"
SETUP_ONLY=false
if [ "${4:-}" = "--setup-only" ]; then
    SETUP_ONLY=true
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

TOPOLOGY_FILE="$AWS_ENVIRONMENT_DIR/topology_setup/topology.json"
CONFIG_TEMPLATE="$SCRIPT_DIR/config.json"
CONFIG_FILE="$QE_TESTS_DIR/config.json"
TOPOLOGY_ROLLING_TEMPLATE="$SCRIPT_DIR/topology_rolling.json"

init_greenboard_results_dir
trap 'uv run python -m cbltest.greenboard_upload \
    --config "$CONFIG_FILE" \
    --results-dir "$GREENBOARD_RESULTS_DIR" \
    --upgrade-to "$SGW_TO" || true' EXIT

echo ">>> Initial setup of 3-node SGW cluster with $SGW_FROM ..."
pushd $AWS_ENVIRONMENT_DIR > /dev/null
uv run $SCRIPT_DIR/setup_test.py $CBL_VERSION $SGW_FROM --topology-file $TOPOLOGY_ROLLING_TEMPLATE
popd > /dev/null

if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

echo ">>> Pre-upgrade pytest ..."
pushd $QE_TESTS_DIR > /dev/null
uv run pytest -s -v --no-header -W ignore::DeprecationWarning \
    --config config.json -m upg_sgw \
    --junitxml="$GREENBOARD_RESULTS_DIR/junit_rolling_pre.xml" \
    test_rolling_upgrade_sgw.py
popd > /dev/null

echo ">>> Rolling upgrade nodes 0,1,2 to $SGW_TO ..."
for node_index in 0 1 2; do
    echo "--> Destroying SGW node $node_index ..."
    pushd $AWS_ENVIRONMENT_DIR > /dev/null
    uv run ./stop_backend.py \
        --topology topology_setup/topology.json \
        --destroy-sgw --sgw-index $node_index \
        --no-ts-stop
    popd > /dev/null

    echo "--> Updating topology SGW node $node_index version to $SGW_TO ..."
    pushd $AWS_ENVIRONMENT_DIR > /dev/null
    uv run $SCRIPT_DIR/update_sgw_version.py topology_setup/topology.json $SGW_TO $node_index
    popd > /dev/null

    echo "--> Recreating SGW node $node_index instance via terraform ..."
    pushd $AWS_ENVIRONMENT_DIR > /dev/null
    uv run ./start_backend.py \
        --topology $TOPOLOGY_FILE \
        --tdk-config-in $CONFIG_TEMPLATE \
        --tdk-config-out $CONFIG_FILE \
        --no-cbs-provision \
        --no-sgw-provision \
        --no-es-provision \
        --no-lb-provision \
        --no-ls-provision \
        --no-ts-run
    popd > /dev/null

    echo "--> Provisioning only SGW node $node_index with $SGW_TO ..."
    pushd $AWS_ENVIRONMENT_DIR > /dev/null
    uv run $SCRIPT_DIR/provision_single_sgw.py $node_index \
        --topology topology_setup/topology.json
    popd > /dev/null
done

echo ">>> Post-upgrade pytest ..."
pushd $QE_TESTS_DIR > /dev/null
uv run pytest -s -v --no-header -W ignore::DeprecationWarning \
    --config config.json -m upg_sgw \
    --junitxml="$GREENBOARD_RESULTS_DIR/junit_rolling_post.xml" \
    test_rolling_upgrade_sgw.py
popd > /dev/null

echo ">>> SGW rolling upgrade test completed successfully."
