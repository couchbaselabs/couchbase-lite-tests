#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ES_VERSION="${1:-1.0.1}"
TEST_NAME="${2:-.}"
TOPOLOGY_NAME="${3:-es_sgw_topology.json}"
SGW_VERSION="${4:-}"
CBS_VERSION="${5:-}"
DATASET_VERSION="${6:-4.0}"
CBL_VERSION="${7:-}"  # version-build for the topology's test servers (e.g. the localhost JS test server)
JS_ONLY="${8:-false}" # true: run only the tests that replicate with a CBL test server
TOPOLOGY_FILE="$SCRIPT_DIR/topologies/$TOPOLOGY_NAME"

if [ -z "$SGW_VERSION" ]; then
  echo "SGW_VERSION not set: setup uses the latest GA Sync Gateway and Couchbase Server"
fi

source $SCRIPT_DIR/../../shared/config.sh

if [ -z "$TEST_NAME" ]; then
  echo "TEST_NAME is required (use \".\" to run all tests)"
  exit 1
fi

# Every test that needs an Edge Server. Tests whose other min_* markers this
# topology can't satisfy are skipped by the required_topology plugin.
MARKER="min_edge_servers"
if [ "$JS_ONLY" = "true" ]; then
  MARKER="min_edge_servers and min_test_servers"
fi

PYTEST_ARGS=(
  -v --no-header -W ignore::DeprecationWarning
  --config config.json
  --dataset-version "$DATASET_VERSION"
  # When a test fails, collect logs from every Edge Server node into the current
  # directory (es-collect-<host>-<timestamp>.tar.gz); teardown archives them.
  --es-collect
  -m "$MARKER"
)
# TEST_NAME "." runs every selected test; anything else is passed to pytest -k.
if [ "$TEST_NAME" != "." ]; then
  PYTEST_ARGS+=(-k "$TEST_NAME")
fi

echo "Setup backend..."
uv run $SCRIPT_DIR/setup_test.py $ES_VERSION $TOPOLOGY_FILE --sgw-version "${SGW_VERSION:-}" --cbs-version "${CBS_VERSION:-}" --cbl-version "${CBL_VERSION:-}"

export COLUMNS=200
echo "RUNNING COORDINATED TEST (TEST_NAME=$TEST_NAME, JS_ONLY=$JS_ONLY)"
pushd "$FUNCTIONAL_TESTS_DIR" >/dev/null
TEST_RESULT=0
uv run pytest "${PYTEST_ARGS[@]}" || TEST_RESULT=1
popd >/dev/null

echo "========== PYTEST OUTPUT END =========="
if [ "$TEST_RESULT" -eq 0 ]; then
  echo "🎉 COORDINATED TEST PASSED!"
else
  echo "💥 COORDINATED TEST FAILED!"
fi
exit $TEST_RESULT
