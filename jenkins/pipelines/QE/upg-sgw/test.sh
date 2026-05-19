#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
    echo "Usage: $0 <cbl_version> <sgw_from> <sgw_to> [--setup-only]"
    echo "  <cbl_version>: The Couchbase Lite version to test against."
    echo "  <sgw_from>:    The starting Sync Gateway version."
    echo "  <sgw_to>:      The target Sync Gateway version to upgrade to."
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

echo ">>> Initial setup with SGW: $SGW_FROM ..."
pushd $AWS_ENVIRONMENT_DIR > /dev/null
uv run $SCRIPT_DIR/setup_test.py $CBL_VERSION $SGW_FROM
popd > /dev/null

if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

echo ">>> Pre-upgrade pytest (seed; result NOT uploaded to greenboard) ..."
pushd $QE_TESTS_DIR > /dev/null
uv run pytest -s -v --no-header -W ignore::DeprecationWarning \
    --config config.json --no-result-upload -m upg_sgw \
    test_upg_sgw.py
popd > /dev/null

echo ">>> Upgrading SGW from $SGW_FROM to $SGW_TO ..."
pushd $AWS_ENVIRONMENT_DIR > /dev/null
uv run $SCRIPT_DIR/update_sgw_version.py topology_setup/topology.json $SGW_TO
uv run ./start_backend.py \
    --topology $TOPOLOGY_FILE \
    --tdk-config-in $CONFIG_TEMPLATE \
    --tdk-config-out $CONFIG_FILE \
    --no-cbs-provision \
    --no-es-provision \
    --no-lb-provision \
    --no-ls-provision \
    --no-ts-run
popd > /dev/null

echo ">>> Post-upgrade pytest (uploads pass/fail to sgw-upgrade::waterfall doc) ..."
export SGW_UPGRADE_FROM="$SGW_FROM"
export SGW_UPGRADE_TO="$SGW_TO"
pushd $QE_TESTS_DIR > /dev/null
uv run pytest -s -v --no-header -W ignore::DeprecationWarning \
    --config config.json -m upg_sgw \
    test_upg_sgw.py
popd > /dev/null

echo ">>> SGW upgrade test completed successfully."
