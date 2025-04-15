#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

function usage() {
    echo "Usage: $0 <version> <dataset_version> <platform> <sgw_version> [private_key_path]"
    echo "version: CBL version (e.g. 3.2.1-2)"
    echo "dataset_version: Version of the Couchbase Lite datasets to use"
    echo "platform: The .NET platform to build (e.g. ios)"
    echo "sgw_version: Version of Sync Gateway to download and use"
    echo "private_key_path: Path to the private key to use for SSH connections"
}

if [ $# -lt 4 ]; then
    usage
    exit 1
fi

if [ $# -gt 4 ]; then
    private_key_path=$5
fi

cbl_version=$1
dataset_version=$2
platform=$3
sgw_version=$4

python3 -m venv venv
source venv/bin/activate
pip install -r $SCRIPT_DIR/../../../environment/aws/requirements.txt
if [ -n "$private_key_path" ]; then
    python3 $SCRIPT_DIR/setup_test.py $platform $cbl_version $dataset_version $sgw_version --private_key $private_key_path
else
    python3 $SCRIPT_DIR/setup_test.py $platform $cbl_version $dataset_version $sgw_version
fi

pushd $SCRIPT_DIR/../../../tests/dev_e2e
pip install -r requirements.txt
pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json
deactivate