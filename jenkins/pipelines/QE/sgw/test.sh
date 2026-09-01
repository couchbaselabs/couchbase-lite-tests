#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
  echo "Usage: $0 <version> <sgw_version> [--test-filter EXPR] [--setup-only]"
  echo "  <cbl_version>: The Couchbase Lite version to run the test against."
  echo "  <sgw_version>: Sync Gateway version to be deployed for the test."
  echo "  --test-filter: An optional pytest -k filter expression"
  echo "  --setup-only: Only build test server and setup backend, skip test execution"
  echo "  Build number will be auto-fetched for the specified version"
  exit 1
}

if [ "$#" -lt 2 ]; then usage; fi

CBL_VERSION=${1}
SGW_VERSION=${2}
shift 2

TEST_FILTER=""
SETUP_ONLY=false
while [ "$#" -gt 0 ]; do
  case "$1" in
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
uv run "$SCRIPT_DIR"/setup_test.py "$CBL_VERSION" "$SGW_VERSION"
popd >/dev/null

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
  echo "Setup completed. Exiting due to --setup-only flag."
  exit 0
fi

# test_replication_xdcr.py needs two separate Couchbase Server clusters, which
# this single-cluster topology does not provide; it is deferred until the
# multi-cluster topology is sorted out rather than left to fail every night. See CBL-8686

section_start "$COLOR_YELLOW" "RUN TESTS"
pushd "$TESTS_DIR" >/dev/null
if [ -n "$TEST_FILTER" ]; then
  uv run pytest -v --no-header --config QE/config.json \
    --ignore=dev_e2e/test_replication_xdcr.py \
    --sgcollect-on-test-failure \
    -k "$TEST_FILTER" \
    --no-result-upload
else
  uv run pytest -v --no-header --config QE/config.json \
    --ignore=dev_e2e/test_replication_xdcr.py \
    --sgcollect-on-test-failure
fi
