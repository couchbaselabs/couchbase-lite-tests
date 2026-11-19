#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
  echo "Usage: $0 <version> <sgw_version> [--es-version VERSION] [--dataset-version VERSION] [--test-filter EXPR] [--setup-only]"
  echo "  <cbl_version>: The Couchbase Lite version to run the test against."
  echo "  <sgw_version>: Sync Gateway version to be deployed for the test."
  echo "  --dataset-version: Version of CBL dataset to use (default: 4.0)"
  echo "  --es-version: Edge Server version (default: the latest release)"
  echo "  --test-filter: An optional pytest -k filter expression"
  echo "  --setup-only: Only build test server and setup backend, skip test execution"
  echo "  Build number will be auto-fetched for the specified version"
  exit 1
}

if [ "$#" -lt 2 ]; then usage; fi

CBL_VERSION=${1}
SGW_VERSION=${2}
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source "$SCRIPT_DIR"/../../shared/config.sh

section_start "$COLOR_CYAN" "INFRA SETUP"
pushd "$AWS_ENVIRONMENT_DIR" >/dev/null
uv run "$SCRIPT_DIR"/setup_test.py "$CBL_VERSION" "$SGW_VERSION" ${ES_VERSION:+--es-version "$ES_VERSION"}
popd >/dev/null
section_end

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
  echo "Setup completed. Exiting due to --setup-only flag."
  exit 0
fi

section_start "$COLOR_YELLOW" "RUN TESTS"
pushd "$FUNCTIONAL_TESTS_DIR" >/dev/null
# Every test that needs a Sync Gateway. Tests whose other min_* markers this
# topology can't satisfy (e.g. a second test server) are skipped by the required_topology plugin.
PYTEST_ARGS=(
  -v --no-header --config config.json
  --ignore=test_query_consistency.py
  --dataset-version "$DATASET_VERSION"
  --sgcollect-on-test-failure
  --cbcollect-on-test-failure
  -m min_sync_gateways
)
if [ -n "$TEST_FILTER" ]; then
  PYTEST_ARGS+=(-k "$TEST_FILTER" --no-result-upload)
fi
uv run pytest "${PYTEST_ARGS[@]}"
popd >/dev/null
section_end
