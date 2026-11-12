#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ES_VERSION="${1:-1.0.1}"
TEST_FILTER="${2:-}"
SGW_VERSION="${3:-}"
CBL_VERSION="${4:?CBL_VERSION is required: the version-build of the localhost JS test server}"
JS_ONLY="${5:-false}" # true: run only the tests that replicate with the CBL test server
STRESS="${6:-false}"  # true: run only the stress tests (tests/functional/stress) in place of the regular ones
# Edge Server only works with the 3.x datasets, as does the CBL JS test server.
DATASET_VERSION="3.2"

if [ -z "$SGW_VERSION" ]; then
  echo "SGW_VERSION not set: setup uses the latest GA Sync Gateway"
fi

source $SCRIPT_DIR/../../shared/config.sh

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
if [ "$STRESS" = "true" ]; then
  PYTEST_ARGS+=(--stress)
fi
# An empty TEST_FILTER runs every selected test; anything else is passed to pytest -k.
if [ -n "$TEST_FILTER" ]; then
  PYTEST_ARGS+=(-k "$TEST_FILTER")
fi

echo "Setup backend..."
uv run $SCRIPT_DIR/setup_test.py $ES_VERSION --sgw-version "${SGW_VERSION:-}" --cbl-version "$CBL_VERSION"

export COLUMNS=200
echo "RUNNING COORDINATED TEST (TEST_FILTER=$TEST_FILTER, JS_ONLY=$JS_ONLY, STRESS=$STRESS)"
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
