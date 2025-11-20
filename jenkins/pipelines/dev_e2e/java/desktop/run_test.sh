#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../../shared/config.sh

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

stop_venv
create_venv venv
source venv/bin/activate
trap stop_venv EXIT
uv pip install -r $AWS_ENVIRONMENT_DIR/requirements.txt
python3 $SCRIPT_DIR/setup_test.py $cbl_version $sgw_version

pushd $DEV_E2E_TESTS_DIR
uv pip install -r requirements.txt
pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json
deactivate