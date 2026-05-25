#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ES_VERSION="${1:-1.0.1}"
TEST_NAME="${2:-test_crud.py}"
TOPOLOGY_NAME="${3:-es_sgw_topology.json}"
SGW_VERSION="${4:-}"
CBS_VERSION="${5:-}"
TOPOLOGY_FILE="$SCRIPT_DIR/topologies/$TOPOLOGY_NAME"

if [ -z "$SGW_VERSION" ]; then
    echo "Skipping sync gateway and cb server provisioning"
fi

source $SCRIPT_DIR/../../shared/config.sh

init_greenboard_results_dir
trap 'uv run python -m cbltest.greenboard_upload \
    --config "$QE_TESTS_DIR/config.json" \
    --results-dir "$GREENBOARD_RESULTS_DIR" || true' EXIT

echo "Setup backend..."
uv run $SCRIPT_DIR/setup_test.py $ES_VERSION $TOPOLOGY_FILE --sgw-version "${SGW_VERSION:-}" --cbs-version "${CBS_VERSION:-}"

# Run Tests :
echo "RUNNING COORDINATED TEST"

pushd "${QE_TESTS_DIR}/edge_server" > /dev/null
export COLUMNS=200

if uv run pytest -v --no-header -W ignore::DeprecationWarning --config ../config.json \
    --junitxml="$GREENBOARD_RESULTS_DIR/junit_qe_es.xml" \
    "$TEST_NAME"; then
    echo "========== PYTEST OUTPUT END =========="
    echo ""
    echo "🎉 COORDINATED TEST PASSED!"
    TEST_RESULT=0
else
    echo "========== PYTEST OUTPUT END =========="
    echo ""
    echo "💥 COORDINATED TEST FAILED!"
    TEST_RESULT=1
fi
