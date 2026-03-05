#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
    echo "Usage: $0 <version> <sgw_version_1> [<sgw_version_2> ... <sgw_version_N>] [--setup-only]"
    echo "  <cbl_version>: The Couchbase Server version to test against."
    echo "  <sgw_version_X>: One or more Sync Gateway versions for the upgrade test."
    echo "  --setup-only: Only build test server and setup backend, skip test execution"
    echo "  Build number will be auto-fetched for the specified version"
    exit 1
}

if [ "$#" -lt 2 ]; then usage; fi

CBL_VERSION=${1}
shift # The rest of the arguments are SGW versions or flags

SETUP_ONLY=false
SGW_VERSIONS=()
for arg in "$@"; do
    if [ "$arg" = "--setup-only" ]; then
        SETUP_ONLY=true
    else
        SGW_VERSIONS+=("$arg")
    fi
done

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

# TOPOLOGY_FILE="$SCRIPT_DIR/topology.json"
# CONFIG_FILE="$SCRIPT_DIR/config.json"

# Initial full setup with the first SGW version
CURRENT_SGW_VERSION="${SGW_VERSIONS[0]}"
echo "Setup backend..."
pushd $AWS_ENVIRONMENT_DIR > /dev/null
uv run --group orchestrator $SCRIPT_DIR/setup_test.py $CBL_VERSION $CURRENT_SGW_VERSION
popd > /dev/null

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

# Run initial tests
echo ">>> Running tests for initial setup with SGW: $CURRENT_SGW_VERSION ..."
export SGW_VERSION_UNDER_TEST="$CURRENT_SGW_VERSION"
pushd $QE_TESTS_DIR > /dev/null
# export UPGRADE_ITERATION=0
uv run pytest -s -v --no-header -W ignore::DeprecationWarning --config config.json -m upg_sgw
popd > /dev/null

# Loop through the remaining SGW versions and perform upgrades
for ((i=1; i<${#SGW_VERSIONS[@]}; i++)); do
    PREVIOUS_SGW_VERSION="$CURRENT_SGW_VERSION"
    CURRENT_SGW_VERSION="${SGW_VERSIONS[i]}"
    echo ">>> Upgrading SGW from $PREVIOUS_SGW_VERSION to $CURRENT_SGW_VERSION ..."

    # 1. Destroy the old Sync Gateway instances ONLY.
    #    --no-ts-stop is used to keep the test servers running during the upgrade.
    echo "--> Destroying old Sync Gateway instances..."
    pushd $AWS_ENVIRONMENT_DIR > /dev/null
    uv run --group orchestrator ./stop_backend.py \
        --topology topology_setup/topology.json \
        --destroy-sgw \
        --no-ts-stop
    popd > /dev/null

    # 2. Re-run start_backend. This will apply terraform to create the new SGW
    #    instances and then provision them with the new software version.
    echo "--> Provisioning new Sync Gateway instances with version $CURRENT_SGW_VERSION..."
    pushd $AWS_ENVIRONMENT_DIR > /dev/null
    # uv run --group orchestrator ./start_backend.py \
    #     --topology topology_setup/topology.json \
    #     --tdk-config-in ../../tests/QE/config.json \
    #     --tdk-config-out ../../tests/QE/config.json \
    #     --no-cbs-provision \
    #     --no-es-provision \
    #     --no-lb-provision \
    #     --no-ls-provision \
    #     --no-ts-run \
    #     --no-terraform-apply
    uv run --group orchestrator $SCRIPT_DIR/setup_test.py $CBL_VERSION $CURRENT_SGW_VERSION
    popd > /dev/null

    echo ">>> Running tests after upgrading to SGW: $CURRENT_SGW_VERSION ..."
    export SGW_VERSION_UNDER_TEST="$CURRENT_SGW_VERSION"
    pushd $QE_TESTS_DIR > /dev/null
    # export UPGRADE_ITERATION=$i
    uv run pytest -s -v --no-header -W ignore::DeprecationWarning --config config.json -m upg_sgw
    popd > /dev/null
done

echo ">>> Upgrade test completed successfully."