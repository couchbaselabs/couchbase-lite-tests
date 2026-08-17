#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
  echo "Usage: $0 <cbl_version> <sgw_version> [--setup-only | --skip-setup]"
  echo "  <cbl_version>: The Couchbase Lite version to run the test against."
  echo "  <sgw_version>: Sync Gateway version to be deployed for the test."
  echo "  --setup-only: Only build test server and setup backend, skip test execution"
  echo "  --skip-setup: Skip setup, only run the tests against an already-provisioned backend"
  echo "  Build number will be auto-fetched for the specified version"
  exit 1
}

if [ "$#" -lt 2 ]; then usage; fi

CBL_VERSION=${1}
SGW_VERSION=${2}
shift 2

# The two positionals must be versions, not flags (catches e.g. a flag placed
# in the version position).
case "$CBL_VERSION" in -*) usage ;; esac
case "$SGW_VERSION" in -*) usage ;; esac
SETUP_ONLY=false
SKIP_SETUP=false

# Parse only the optional flags that follow the versions; anything unrecognized
# (a typo, or a stray positional) is an explicit error rather than silently ignored.
for arg in "$@"; do
  case "$arg" in
    --setup-only) SETUP_ONLY=true ;;
    --skip-setup) SKIP_SETUP=true ;;
    *) usage ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source "$SCRIPT_DIR"/../../shared/config.sh

if [ "$SKIP_SETUP" != true ]; then
  echo "Setup backend..."
  pushd "$AWS_ENVIRONMENT_DIR" >/dev/null
  uv run "$SCRIPT_DIR"/setup_test.py "$CBL_VERSION" "$SGW_VERSION"
  popd >/dev/null
fi

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
  echo "Setup completed. Exiting due to --setup-only flag."
  exit 0
fi

# test_replication_xdcr.py needs two separate Couchbase Server clusters, which
# this single-cluster topology does not provide; it is deferred until the
# multi-cluster topology is sorted out rather than left to fail every night. See CBL-8686

echo "Run tests..."
pushd "$TESTS_DIR" >/dev/null
# --session-timeout makes pytest stop gracefully BEFORE Jenkins' 90m tests-phase timeout, so junit, greenboard,
# and sgcollect cleanup all get a runway, and infra-setup no longer eats the budget, ie:
#   session-timeout = jenkins-tests(90m) - per-test(5m) - artifact-collection(10m) = 75m = 4500s
# --timeout bounds a single hung test (session-timeout is only checked between tests); method=signal raises in the
# main thread so that test's teardown runs.
uv run pytest -v --no-header --config QE/config.json --sgcollect-on-test-failure --timeout-method=signal \
  --timeout=300 --session-timeout=4500 --ignore=dev_e2e/test_replication_xdcr.py
