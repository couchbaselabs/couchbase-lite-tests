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
TEST_DIR="${7:-QE}" # QE | dev_e2e | both
TOPOLOGY_FILE="$SCRIPT_DIR/topologies/$TOPOLOGY_NAME"

if [ -z "$SGW_VERSION" ]; then
  echo "Skipping sync gateway and cb server provisioning"
fi

source $SCRIPT_DIR/../../shared/config.sh

# TEST_DIR picks which edge_server test directory (or both) to run.
case "$TEST_DIR" in
  QE) SUITE_DIRS=("$QE_TESTS_DIR/edge_server") ;;
  dev_e2e) SUITE_DIRS=("$DEV_E2E_TESTS_DIR/edge_server") ;;
  both) SUITE_DIRS=("$QE_TESTS_DIR/edge_server" "$DEV_E2E_TESTS_DIR/edge_server") ;;
  *)
    echo "Invalid TEST_DIR '$TEST_DIR' (expected QE, dev_e2e or both)"
    exit 1
    ;;
esac

# TEST_NAME "." runs everything in the selected directory; anything else is
# passed to pytest -k, which is only allowed for a single directory.
if [ -z "$TEST_NAME" ]; then
  echo "TEST_NAME is required (use \".\" to run all tests)"
  exit 1
fi
PYTEST_FILTER=()
if [ "$TEST_NAME" != "." ]; then
  if [ "$TEST_DIR" = "both" ]; then
    echo "TEST_NAME '$TEST_NAME' cannot be used with TEST_DIR=both; use \".\" or pick QE or dev_e2e"
    exit 1
  fi
  PYTEST_FILTER=(-k "$TEST_NAME")
fi

echo "Setup backend..."
uv run $SCRIPT_DIR/setup_test.py $ES_VERSION $TOPOLOGY_FILE --sgw-version "${SGW_VERSION:-}" --cbs-version "${CBS_VERSION:-}"

export COLUMNS=200
TEST_RESULT=0

# Each directory runs as its own pytest session against the same backend.
# A failure in one does not stop the next; the script fails if any failed.
for suite_dir in "${SUITE_DIRS[@]}"; do
  echo "RUNNING COORDINATED TEST ($suite_dir, TEST_NAME=$TEST_NAME)"
  pushd "$suite_dir" >/dev/null

  if uv run pytest -v --no-header -W ignore::DeprecationWarning --config "$QE_TESTS_DIR/config.json" --dataset-version "$DATASET_VERSION" ${PYTEST_FILTER[@]+"${PYTEST_FILTER[@]}"} .; then
    echo "========== PYTEST OUTPUT END =========="
    echo ""
    echo "🎉 COORDINATED TEST PASSED! ($suite_dir)"
  else
    echo "========== PYTEST OUTPUT END =========="
    echo ""
    echo "💥 COORDINATED TEST FAILED! ($suite_dir)"
    TEST_RESULT=1
  fi

  popd >/dev/null
done

exit $TEST_RESULT
