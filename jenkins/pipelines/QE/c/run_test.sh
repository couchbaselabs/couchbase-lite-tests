#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../shared/config.sh

function usage() {
    echo "Usage: $0 <version> <platform> <sgw_version> [dataset_version] [--setup-only]"
    echo "version: CBL version (e.g. 3.2.1-2)"
    echo "platform: The C platform to build (e.g. ios)"
    echo "sgw_version: Version of Sync Gateway to download and use"
    echo "dataset_version: Optional dataset version (default: 4.0)"
    echo "  --setup-only: Only build test server and setup backend, skip test execution"
}

if [ $# -lt 3 ]; then
    usage
    exit 1
fi

cbl_version=$1
platform=$2
sgw_version=$3

SETUP_ONLY=false
DATASET_VERSION="4.0"

# Parse optional arguments
for arg in "${@:4}"; do
    case "$arg" in
        --setup-only)
            SETUP_ONLY=true
            ;;
        *)
            DATASET_VERSION="$arg"
            ;;
    esac
done

uv run $SCRIPT_DIR/setup_test.py $platform $cbl_version $sgw_version

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

pushd $QE_TESTS_DIR
uv run pytest -v --no-header -W ignore::DeprecationWarning \
    --config config.json \
    --dataset-version "$DATASET_VERSION" \
    -m cbl
