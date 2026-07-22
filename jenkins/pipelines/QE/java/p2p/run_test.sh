#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR/../../../shared/config.sh"

function usage() {
    echo "Usage: $0 <version> [dataset_version]"
    echo "version: CBL version (e.g. 3.2.1-2)"
    echo "dataset_version: Optional dataset version (default: 4.0)"
}

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    usage
    exit 1
fi

cbl_version=$1
DATASET_VERSION="${2:-4.0}"

uv run "$SCRIPT_DIR/setup_test.py" "$cbl_version"

pushd "$QE_TESTS_DIR"

uv run pytest --maxfail=7 -W ignore::DeprecationWarning \
    --config config.json \
    --dataset-version "$DATASET_VERSION" \
    test_peer_to_peer.py