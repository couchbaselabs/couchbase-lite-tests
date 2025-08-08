#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../../shared/config.sh

function usage() {
    echo "Usage: $0 <version> <sgw_version> [private_key_path]"
    echo "version: CBL version (e.g. 3.2.1-2)"
    echo "sgw_version: Version of Sync Gateway to download and use"
    echo "private_key_path: Path to the private key to use for SSH connections"
}

if [ $# -lt 2 ]; then
    usage
    exit 1
fi

if [ $# -gt 2 ]; then
    private_key_path=$3
fi

cbl_version=$1
sgw_version=$2

if [ -n "$private_key_path" ]; then
    uv run --project $AWS_ENVIRONMENT_DIR/pyproject.toml $SCRIPT_DIR/setup_test.py $cbl_version $sgw_version --private_key $private_key_path
else
    uv run --project $AWS_ENVIRONMENT_DIR/pyproject.toml $SCRIPT_DIR/setup_test.py $cbl_version $sgw_version
fi

pushd $DEV_E2E_TESTS_DIR
uv run pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json