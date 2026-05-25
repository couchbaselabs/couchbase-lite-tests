#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../../shared/config.sh

init_greenboard_results_dir
trap 'uv run python -m cbltest.greenboard_upload \
    --config "$QE_TESTS_DIR/config.json" \
    --results-dir "$GREENBOARD_RESULTS_DIR" || true' EXIT

function usage() {
    echo "Usage: $0 <version> <sgw_version> [private_key_path]"
    echo "version: CBL version (e.g. 3.2.1-2)"
    echo "sgw_version: Version of Sync Gateway to download and use"
}

if [ $# -ne 2 ]; then
    usage
    exit 1
fi

cbl_version=$1
sgw_version=$2

uv run $SCRIPT_DIR/setup_test.py $cbl_version $sgw_version

pushd $QE_TESTS_DIR
uv run pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json \
    --junitxml="$GREENBOARD_RESULTS_DIR/junit_qe_java_webservice.xml" \
    -m cbl
