#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

# Aggregated greenboard upload: per-iteration results are written to this
# file by the greenboard pytest fixture, and a single batch document is
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
    echo "Usage: $0 <cbl_version> <sgw_version_1> [<sgw_version_2> ... <sgw_version_N>] [--setup-only]"
    echo "  <cbl_version>: The Couchbase Lite version to test against."
    echo "  <sgw_version_X>: One or more Sync Gateway versions for the rolling upgrade test."
    echo "  --setup-only: Only build test servers and setup backend, skip test execution"
    echo "  Build number will be auto-fetched for the specified version"
    exit 1
}

if [ "$#" -lt 2 ]; then usage; fi

CBL_VERSION=${1}
shift

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

# Store the rolling topology template for reuse
TOPOLOGY_ROLLING_TEMPLATE="$SCRIPT_DIR/topology_rolling.json"

# Function to perform a rolling upgrade: upgrade one node at a time
function rolling_upgrade_to_version() {
    local target_version=$1
    local previous_version=$2

    echo ">>> ================================================================"
    echo ">>> ROLLING UPGRADE: $previous_version → $target_version"
    echo ">>> ================================================================"

    # Phase: initial (before any rolling)
    if [ "$previous_version" = "initial" ]; then
        echo ">>> Phase: INITIAL SETUP with SGW version $target_version"
        export SGW_VERSION_UNDER_TEST="$target_version"
        export SGW_UPGRADE_PHASE="initial"
        unset SGW_UPGRADED_NODE_INDEX 2>/dev/null || true
        unset SGW_PREVIOUS_VERSION 2>/dev/null || true

        pushd $QE_TESTS_DIR > /dev/null
        uv run pytest -s -v --no-header -W ignore::DeprecationWarning --config config.json -m upg_sgw \
            --upgrade-versions "$UPGRADE_VERSIONS" \
            test_rolling_upgrade_sgw.py
        popd > /dev/null
    else
        # Rolling upgrade: upgrade nodes one at a time
        for node_index in 0 1 2; do
            echo ""
            echo ">>> Phase: ROLLING UPGRADE node $node_index from $previous_version to $target_version"

            # 1. Destroy single SGW node
            echo "--> Destroying SGW node $node_index..."
            pushd $AWS_ENVIRONMENT_DIR > /dev/null
            uv run ./stop_backend.py \
                --topology topology_setup/topology.json \
                --destroy-sgw --sgw-index $node_index \
                --no-ts-stop
            popd > /dev/null

            # 2. Update topology with new SGW version for this specific node only
            echo "--> Updating topology SGW node $node_index to version $target_version..."
            pushd $AWS_ENVIRONMENT_DIR > /dev/null
            uv run $SCRIPT_DIR/update_sgw_version.py topology_setup/topology.json $target_version $node_index
            popd > /dev/null

            # 3. Recreate the destroyed instance via terraform (skip all provisioning)
            echo "--> Recreating SGW node $node_index instance via terraform..."
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

            # 4. Provision only the single upgraded SGW node
            echo "--> Provisioning only SGW node $node_index with version $target_version..."
            pushd $AWS_ENVIRONMENT_DIR > /dev/null
            uv run $SCRIPT_DIR/provision_single_sgw.py $node_index \
                --topology topology_setup/topology.json
            popd > /dev/null

            # 4. Run rolling upgrade test for this node
            echo ""
            echo ">>> Running rolling upgrade test for node $node_index..."
            export SGW_UPGRADE_PHASE="rolling_node_$node_index"
            export SGW_UPGRADED_NODE_INDEX=$node_index
            export SGW_VERSION_UNDER_TEST="$target_version"
            export SGW_PREVIOUS_VERSION="$previous_version"

            pushd $QE_TESTS_DIR > /dev/null
            uv run pytest -s -v --no-header -W ignore::DeprecationWarning --config config.json -m upg_sgw \
                --upgrade-versions "$UPGRADE_VERSIONS" \
                test_rolling_upgrade_sgw.py
            popd > /dev/null
        done

        # Final phase: all nodes upgraded
        echo ""
        echo ">>> Phase: COMPLETE - All SGW nodes upgraded to $target_version"
        export SGW_UPGRADE_PHASE="complete"
        unset SGW_UPGRADED_NODE_INDEX 2>/dev/null || true
        export SGW_VERSION_UNDER_TEST="$target_version"
        export SGW_PREVIOUS_VERSION="$previous_version"

        pushd $QE_TESTS_DIR > /dev/null
        uv run pytest -s -v --no-header -W ignore::DeprecationWarning --config config.json -m upg_sgw \
            --upgrade-versions "$UPGRADE_VERSIONS" \
            test_rolling_upgrade_sgw.py
        popd > /dev/null
    fi
}

# === Main Flow ===

FIRST_VERSION="true"
PREVIOUS_VERSION="initial"

for SGW_VERSION in "${SGW_VERSIONS[@]}"; do
    if [ "$FIRST_VERSION" = "true" ]; then
        # Full setup with the first SGW version (all 3 nodes provisioned at once)
        echo ">>> Initial full setup with SGW version $SGW_VERSION using rolling topology (3 SGW nodes)..."
        pushd $AWS_ENVIRONMENT_DIR > /dev/null
        uv run $SCRIPT_DIR/setup_test.py $CBL_VERSION $SGW_VERSION --topology-file $TOPOLOGY_ROLLING_TEMPLATE
        popd > /dev/null

        FIRST_VERSION="false"

        if [ "$SETUP_ONLY" = true ]; then
            echo "Setup completed. Exiting due to --setup-only flag."
            exit 0
        fi

        # Run initial phase test
        rolling_upgrade_to_version "$SGW_VERSION" "initial"
        PREVIOUS_VERSION="$SGW_VERSION"
    else
        # Rolling upgrade to this version
        rolling_upgrade_to_version "$SGW_VERSION" "$PREVIOUS_VERSION"
        PREVIOUS_VERSION="$SGW_VERSION"
    fi
done

echo ">>> SGW Rolling Upgrade test completed successfully."
