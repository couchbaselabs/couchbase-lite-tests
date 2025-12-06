#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../shared/config.sh

function usage() {
    echo "Usage: $0 <version> <platform> <sgw_version> [private_key_path]"
    echo "version: CBL version (e.g. 3.2.1-2)"
    echo "platform: The C platform to build (e.g. ios)"
    echo "sgw_version: Version of Sync Gateway to download and use"
}

if [ $# -lt 3 ]; then
    usage
    exit 1
fi

cbl_version=$1
platform=$2
sgw_version=$3
dataset_version=${4:-"4.0"}

stop_venv
create_venv venv
source venv/bin/activate
trap stop_venv EXIT
uv pip install -r $AWS_ENVIRONMENT_DIR/requirements.txt
python3 $SCRIPT_DIR/setup_test.py $platform $cbl_version $sgw_version

pushd $DEV_E2E_TESTS_DIR
uv pip install -r requirements.txt
pytest -v --no-header -W ignore::DeprecationWarning --config config.json --dataset-version $dataset_version
deactivate