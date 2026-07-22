#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR"/../../shared/config.sh

function usage() {
    echo "Usage: $0 <version> <platform> <sgw_version> [dataset_version] [--setup-only]"
    echo "  <cbl_version>: The Couchbase Lite version to run the test against."
    echo "  <sgw_version>: Sync Gateway version to be deployed for the test."
    echo "  dataset_version: Optional dataset version (default: 4.0)"
    echo "  --setup-only: Only build test server and setup backend, skip test execution"
}

if [ $# -lt 2 ]; then
    usage
    exit 1
fi

CBL_VERSION=${1}
SGW_VERSION=${2}
DATASET_VERSION="4.0"
SETUP_ONLY=false

# Parse optional arguments
for arg in "$@"; do
    case "$arg" in
        --setup-only)
            SETUP_ONLY=true
            ;;
        *)
            DATASET_VERSION="$arg"
            ;;
    esac
done

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source "$SCRIPT_DIR"/../../shared/config.sh

echo "Setup backend..."
pushd "$AWS_ENVIRONMENT_DIR" > /dev/null
uv run "$SCRIPT_DIR"/setup_test.py "$CBL_VERSION" "$SGW_VERSION"
popd > /dev/null

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

# Run Tests :
echo "Run tests..."
pushd "$DEV_E2E_TESTS_DIR" > /dev/null
uv run pytest -v --no-header -W ignore::DeprecationWarning --config config.json \
    --dataset-version "$DATASET_VERSION" \
    -m sgw \
    --sgcollect-on-test-failure
