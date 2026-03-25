#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
    echo "Usage: $0 <cbl_version> <sg_version> [dataset_version]"
    exit 1
}

if [ "$#" -lt 2 ] ; then usage; fi

CBL_VERSION="$1"
if [ -z "$CBL_VERSION" ]; then usage; fi

SG_VERSION="$2"
if [ -z "$SG_VERSION" ]; then usage; fi
DATASET_VERSION=${3:-"4.0"}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

uv run $SCRIPT_DIR/setup_test.py $CBL_VERSION $SG_VERSION

pushd $DEV_E2E_TESTS_DIR > /dev/null
rm -rf http_log testserver.log

echo "Run the React Native iOS tests"
uv run pytest \
    --maxfail=7 \
    -v \
    -W ignore::DeprecationWarning \
    --config config.json \
    --dataset-version $DATASET_VERSION \
    --ignore=test_multipeer.py \
    -k "not listener and not multipeer and not filter and not custom_conflict" \
    --tb=short \
    --timeout=300
