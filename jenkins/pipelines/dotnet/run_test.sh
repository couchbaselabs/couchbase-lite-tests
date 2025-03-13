#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source $SCRIPT_DIR/test_common.sh

function usage() {
    echo "Usage: $0 <version> <dataset_version> <platform> <sgw_url>"
    echo "version: CBL version (e.g. 3.2.1-2)"
    echo "dataset_version: Version of the Couchbase Lite datasets to use"
    echo "platform: The .NET platform to build (e.g. ios)"
    echo "sgw_url: URL of Sync Gateway to download and use"
}

function prepare_dotnet() {
    if [ $# -ne 1 ]; then
        echo "No dataset version provided to prepare_dotnet!"
        exit 1
    fi

    source $SCRIPT_DIR/prepare_env.sh
    install_dotnet
    install_maui
    if [ "$platform" != "macos" ]; then
        install_xharness
    fi
    copy_datasets $1
}

if [ $# -lt 4 ]; then
    usage
    exit 1
fi

cbl_version=$1
dataset_version=$2
platform=$3
sgw_url=$4

prepare_dotnet $dataset_version

python3 -m venv venv
source venv/bin/activate
pip install -r $SCRIPT_DIR/../../../environment/aws/requirements.txt
python3 ./setup_test.py $platform $cbl_version $sgw_url

pushd $SCRIPT_DIR/../../../tests
pip install -r requirements.txt
pytest -v --no-header --config config.json
deactivate