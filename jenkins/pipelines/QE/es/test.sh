#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ES_VERSION="${1:-1.0.1}"
TEST_NAME="${2:-test_crud.py}"
TOPOLOGY_NAME="${3:-es_sgw_topology.json}"
SGW_VERSION="${4:-}"
CBS_VERSION="${5:-}"
DATASET_VERSION="${6:-4.0}"
TOPOLOGY_FILE="$SCRIPT_DIR/topologies/$TOPOLOGY_NAME"

if [ -z "$SGW_VERSION" ]; then
  echo "Skipping sync gateway and cb server provisioning"
fi

source "$SCRIPT_DIR/../../shared/config.sh"

echo "Setup backend..."
uv run "$SCRIPT_DIR/setup_test.py" "$ES_VERSION" "$TOPOLOGY_FILE" \
  --sgw-version "${SGW_VERSION:-}" --cbs-version "${CBS_VERSION:-}"

echo "RUNNING COORDINATED TEST"

pushd "${QE_TESTS_DIR}/edge_server" >/dev/null
trap 'popd >/dev/null 2>&1 || true' EXIT
export COLUMNS=200

PYTEST_ARGS=(-v --no-header -W ignore::DeprecationWarning
  --config ../config.json
  --dataset-version "$DATASET_VERSION"
  "$TEST_NAME")
[ "${ES_COLLECT:-true}" = "true" ] && PYTEST_ARGS+=(--es-collect)

set +e
uv run pytest "${PYTEST_ARGS[@]}"
TEST_RESULT=$?
set -e

echo "========== PYTEST OUTPUT END =========="
echo ""
if [ "$TEST_RESULT" -eq 0 ]; then
  echo "🎉 COORDINATED TEST PASSED!"
else
  echo "💥 COORDINATED TEST FAILED (pytest exit $TEST_RESULT)!"
fi

exit "$TEST_RESULT"
