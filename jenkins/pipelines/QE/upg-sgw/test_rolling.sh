#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
    echo "Usage: $0 <cbl_version> <sgw_version_1> [<sgw_version_2> ... <sgw_version_N>] [--setup-only]"
    echo "  <cbl_version>: The Couchbase Lite version to test against."
    echo "  <sgw_version_X>: One or more Sync Gateway versions for the rolling upgrade test."
    echo "  --setup-only: Only build test servers and setup backend, skip test execution"
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
        uv run pytest -s -v --no-header -W ignore::DeprecationWarning --config config.json -m upg_sgw test_rolling_upgrade_sgw.py::TestSgwRollingUpgrade::test_rolling_upgrade_sgw_cluster
        popd > /dev/null
    else
        # Rolling upgrade: upgrade nodes one at a time
        for node_index in 0 1 2; do
            echo ""
            echo ">>> Phase: ROLLING UPGRADE node $node_index from $previous_version to $target_version"

            # 1. Destroy single SGW node
            echo "--> Destroying SGW node $node_index..."
            pushd $AWS_ENVIRONMENT_DIR > /dev/null
            uv run --group orchestrator ./stop_backend.py \
                --topology topology_setup/topology.json \
                --destroy-sgw --sgw-index $node_index \
                --no-ts-stop
            popd > /dev/null

            # 2. Update topology with new SGW version
            echo "--> Updating topology with SGW version $target_version..."
            pushd $AWS_ENVIRONMENT_DIR > /dev/null
            uv run $SCRIPT_DIR/update_sgw_version.py topology_setup/topology.json $target_version
            popd > /dev/null

            # 3. Reprovision single SGW node
            echo "--> Provisioning SGW node $node_index with version $target_version..."
            pushd $AWS_ENVIRONMENT_DIR > /dev/null
            uv run --group orchestrator ./start_backend.py \
                --topology $TOPOLOGY_FILE \
                --tdk-config-in $CONFIG_TEMPLATE \
                --tdk-config-out $CONFIG_FILE \
                --no-cbs-provision \
                --no-es-provision \
                --no-lb-provision \
                --no-ls-provision \
                --no-ts-run
            popd > /dev/null

            # 4. Run rolling upgrade test for this node
            echo ""
            echo ">>> Running rolling upgrade test for node $node_index..."
            export SGW_UPGRADE_PHASE="rolling_node_$node_index"
            export SGW_UPGRADED_NODE_INDEX=$node_index
            export SGW_VERSION_UNDER_TEST="$target_version"
            export SGW_PREVIOUS_VERSION="$previous_version"

            pushd $QE_TESTS_DIR > /dev/null
            uv run pytest -s -v --no-header -W ignore::DeprecationWarning --config config.json -m upg_sgw test_rolling_upgrade_sgw.py::TestSgwRollingUpgrade::test_rolling_upgrade_sgw_cluster
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
        uv run pytest -s -v --no-header -W ignore::DeprecationWarning --config config.json -m upg_sgw test_rolling_upgrade_sgw.py::TestSgwRollingUpgrade::test_rolling_upgrade_sgw_cluster
        popd > /dev/null
    fi
}

# === Main Flow ===

FIRST_VERSION="true"
PREVIOUS_VERSION="initial"

for SGW_VERSION in "${SGW_VERSIONS[@]}"; do
    if [ "$FIRST_VERSION" = "true" ]; then
        # Full setup with the first SGW version (all 3 nodes provisioned at once)
        echo ">>> Initial full setup with SGW version $SGW_VERSION..."
        pushd $AWS_ENVIRONMENT_DIR > /dev/null
        uv run --group orchestrator $SCRIPT_DIR/setup_test.py $CBL_VERSION $SGW_VERSION --topology-file $TOPOLOGY_ROLLING_TEMPLATE
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

echo ""
echo ">>> SGW Rolling Upgrade test completed successfully."
