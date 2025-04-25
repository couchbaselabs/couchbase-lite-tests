#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR=$SCRIPT_DIR/../../../..
SHARED_DIR="${SCRIPT_DIR}/../../shared"

function usage() {
    echo "Usage: $0 <version> <dataset_version> <platform> <sgw_version> [private_key_path]"
    echo "version: CBL version (e.g. 3.2.1-2)"
    echo "dataset_version: Version of the Couchbase Lite datasets to use"
    echo "sgw_version: Version of Sync Gateway to download and use"
    echo "private_key_path: Path to the private key to use for SSH connections"
}

if [ $# -lt 3 ]; then
    usage
    exit 1
fi

if [ $# -gt 3 ]; then
    private_key_path=$4
fi

cbl_version=$1
dataset_version=$2
sgw_version=$3

source $SHARED_DIR/check_python_version.sh

create_venv venv
source venv/bin/activate
pip install -r $ROOT_DIR/environment/aws/requirements.txt
if [ -n "$private_key_path" ]; then
    python3 $SCRIPT_DIR/setup_test.py $cbl_version $dataset_version $sgw_version --private_key $private_key_path
else
    python3 $SCRIPT_DIR/setup_test.py $cbl_version $dataset_version $sgw_version
fi

pushd $ROOT_DIR/tests/dev_e2e
pip install -r requirements.txt
pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json
deactivate