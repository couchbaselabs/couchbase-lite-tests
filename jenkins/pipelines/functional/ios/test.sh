#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
  echo "Usage: $0 <cbl_version[-build]> <sgw_version> [--dataset-version VERSION] [--test-filter EXPR] [--setup-only]"
  echo "  cbl_version: x.y.z for the latest build, or x.y.z-build for a specific one"
  echo "  --dataset-version: Version of CBL dataset to use (default: 4.0)"
  echo "  --test-filter: An optional pytest -k filter expression (disables result upload)"
  echo "  --setup-only: Only build test server and setup backend, skip test execution"
  exit 1
}

if [ "$#" -lt 2 ]; then usage; fi

CBL_VERSION=${1}
SGW_VERSION=${2}
shift 2

SETUP_ONLY=false
DATASET_VERSION="4.0"
TEST_FILTER=""

# Parse optional arguments
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dataset-version)
      DATASET_VERSION="$2"
      shift 2
      ;;
    --test-filter)
      TEST_FILTER="$2"
      shift 2
      ;;
    --setup-only)
      SETUP_ONLY=true
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source "$SCRIPT_DIR/../../shared/config.sh"

echo "Setup backend..."

export PATH="/opt/homebrew/bin:$PATH"

uv run "$SCRIPT_DIR/setup_test.py" "$CBL_VERSION" "$SGW_VERSION"

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
  echo "Setup completed. Exiting due to --setup-only flag."
  exit 0
fi

echo "Run tests..."
pushd "${FUNCTIONAL_TESTS_DIR}" >/dev/null
rm -rf http_log testserver.log

# Every test that needs a test server. Tests whose other min_* markers this
# topology can't satisfy are skipped by the required_topology plugin.
PYTEST_ARGS=(
  -v --no-header -W ignore::DeprecationWarning
  --config config.json
  --dataset-version "$DATASET_VERSION"
  -m min_test_servers
)
if [ -n "$TEST_FILTER" ]; then
  PYTEST_ARGS+=(-k "$TEST_FILTER" --no-result-upload)
fi

uv run pytest "${PYTEST_ARGS[@]}"
