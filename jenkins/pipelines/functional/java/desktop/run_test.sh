#!/bin/bash
# Set up the backend, start the Java Desktop test server, and run the functional tests

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
source $SCRIPT_DIR/../../../shared/config.sh

function usage() {
  echo "Usage: $0 <cbl_version[-build]> <sgw_version> [--es-version VERSION] [--dataset-version VERSION] [--test-filter EXPR] [--setup-only]"
  echo "  cbl_version: x.y.z for the latest build, or x.y.z-build for a specific one"
  echo "  sgw_version: Version of Sync Gateway to download and use"
  echo "  --dataset-version: Version of the CBL dataset to use (default: 4.0)"
  echo "  --es-version: Edge Server version (default: the latest release)"
  echo "  --test-filter: An optional pytest -k filter expression (disables result upload)"
  echo "  --setup-only: Only set up the backend and test server, skip test execution"
  exit 1
}

if [ $# -lt 2 ]; then usage; fi

CBL_VERSION=$1
SGW_VERSION=$2
shift 2

DATASET_VERSION="4.0"
TEST_FILTER=""
ES_VERSION=""
SETUP_ONLY=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dataset-version)
      DATASET_VERSION="$2"
      shift 2
      ;;
    --es-version)
      ES_VERSION="$2"
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

uv run $SCRIPT_DIR/setup_test.py "$CBL_VERSION" "$SGW_VERSION" ${ES_VERSION:+--es-version "$ES_VERSION"}

if [ "$SETUP_ONLY" = true ]; then
  echo "Setup completed. Exiting due to --setup-only flag."
  exit 0
fi

pushd $FUNCTIONAL_TESTS_DIR >/dev/null
rm -rf http_log testserver.log

# Every test that needs a test server. Tests whose other min_* markers this
# topology can't satisfy are skipped by the required_topology plugin.
PYTEST_ARGS=(
  -v --no-header --maxfail=7 -W ignore::DeprecationWarning
  --config config.json
  --dataset-version "$DATASET_VERSION"
  -m min_test_servers
)
if [ -n "$TEST_FILTER" ]; then
  PYTEST_ARGS+=(-k "$TEST_FILTER" --no-result-upload)
fi

uv run pytest "${PYTEST_ARGS[@]}"
