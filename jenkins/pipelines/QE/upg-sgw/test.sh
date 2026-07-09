#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

# Aggregated greenboard upload: per-iteration results are written to this
# file by the greenboard pytest fixture; a single batch document is
# uploaded on script exit (success or failure).
export SGW_UPGRADE_RESULTS_FILE="${SGW_UPGRADE_RESULTS_FILE:-/tmp/sgw_upgrade_results.json}"
rm -f "$SGW_UPGRADE_RESULTS_FILE"

function upload_batch_results() {
    local exit_code=$?
    echo ">>> EXIT trap: greenboard batch upload (script exit=$exit_code)"
    if [ ! -f "$SGW_UPGRADE_RESULTS_FILE" ]; then
        echo ">>> No upgrade results file at $SGW_UPGRADE_RESULTS_FILE; skipping batch upload"
        return $exit_code
    fi
    if [ -z "${QE_TESTS_DIR:-}" ] || [ -z "${SCRIPT_DIR:-}" ]; then
        echo ">>> Paths not initialized (QE_TESTS_DIR/SCRIPT_DIR); skipping batch upload"
        return $exit_code
    fi
    echo ">>> Recorded iterations (${SGW_UPGRADE_RESULTS_FILE}):"
    cat "$SGW_UPGRADE_RESULTS_FILE" || true
    echo ""
    echo ">>> Uploading aggregated greenboard batch result..."
    pushd "$QE_TESTS_DIR" > /dev/null || return $exit_code
    set +e
    uv run "$SCRIPT_DIR/upload_greenboard_batch.py" \
        --config config.json \
        --results-file "$SGW_UPGRADE_RESULTS_FILE"
    upload_rc=$?
    set -e
    if [ $upload_rc -ne 0 ]; then
        echo ">>> ERROR: greenboard batch upload failed with exit code $upload_rc"
    else
        echo ">>> Greenboard batch upload completed."
    fi
    popd > /dev/null || true
    return $exit_code
}
trap upload_batch_results EXIT

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

TOPOLOGY_FILE="$AWS_ENVIRONMENT_DIR/topology_setup/topology.json"
CONFIG_TEMPLATE="$SCRIPT_DIR/config.json"
CONFIG_FILE="$QE_TESTS_DIR/config.json"

# Compute comma-separated upgrade path for greenboard
UPGRADE_VERSIONS=$(IFS=,; echo "${SGW_VERSIONS[*]}")

# Initial full setup with the first SGW version
CURRENT_SGW_VERSION="${SGW_VERSIONS[0]}"
echo "Setup backend..."
pushd $AWS_ENVIRONMENT_DIR > /dev/null
uv run $SCRIPT_DIR/setup_test.py $CBL_VERSION $CURRENT_SGW_VERSION
popd > /dev/null

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

# Run initial tests
echo ">>> Running tests for initial setup with SGW: $CURRENT_SGW_VERSION ..."
export SGW_VERSION_UNDER_TEST="$CURRENT_SGW_VERSION"
export SGW_UPGRADE_PHASE="initial"
unset SGW_UPGRADED_NODE_INDEX 2>/dev/null || true
pushd $QE_TESTS_DIR > /dev/null
uv run pytest -s -v --no-header -W ignore::DeprecationWarning --config config.json -m upg_sgw \
    --upgrade-versions "$UPGRADE_VERSIONS" \
    --sgcollect-on-test-failure \
    test_upg_sgw.py
popd > /dev/null

# Loop through the remaining SGW versions and perform upgrades
for ((i=1; i<${#SGW_VERSIONS[@]}; i++)); do

    # Update topology with new SGW version (without resetting CBS/CBL)
    PREVIOUS_SGW_VERSION="$CURRENT_SGW_VERSION"
    CURRENT_SGW_VERSION="${SGW_VERSIONS[i]}"
    echo ">>> Upgrading SGW from $PREVIOUS_SGW_VERSION to $CURRENT_SGW_VERSION ..."
    pushd $AWS_ENVIRONMENT_DIR > /dev/null
    uv run $SCRIPT_DIR/update_sgw_version.py topology_setup/topology.json $CURRENT_SGW_VERSION
    popd > /dev/null

    # Provision new Sync Gateway instances with the updated version.
    echo "--> Provisioning new Sync Gateway instances with version $CURRENT_SGW_VERSION..."
    pushd $AWS_ENVIRONMENT_DIR > /dev/null
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

    echo ">>> Running tests after upgrading to SGW: $CURRENT_SGW_VERSION ..."
    export SGW_VERSION_UNDER_TEST="$CURRENT_SGW_VERSION"
    export SGW_UPGRADE_PHASE="upgrade_to_$CURRENT_SGW_VERSION"
    export SGW_PREVIOUS_VERSION="$PREVIOUS_SGW_VERSION"
    pushd $QE_TESTS_DIR > /dev/null
    uv run pytest -s -v --no-header -W ignore::DeprecationWarning --config config.json -m upg_sgw \
        --upgrade-versions "$UPGRADE_VERSIONS" \
        --sgcollect-on-test-failure \
        test_upg_sgw.py
    popd > /dev/null
done

echo ">>> SGW Upgrade test completed successfully."