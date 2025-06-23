#!/bin/bash -e

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../shared/config.sh

function usage() {
    echo "Usage: $0 <version> <dataset_version> <platform> <sgw_version> [private_key_path] [--setup-only]"
    echo "version: CBL version (e.g. 3.2.1-2)"
    echo "dataset_version: Version of the Couchbase Lite datasets to use"
    echo "platform: The .NET platform to build (e.g. ios)"
    echo "sgw_version: Version of Sync Gateway to download and use"
    echo "private_key_path: Path to the private key to use for SSH connections"
    echo "  --setup-only: Only build test server and setup backend, skip test execution"
}

function prepare_dotnet() {
    source $SCRIPT_DIR/prepare_env.sh
    install_dotnet
    install_maui
    if [ "$platform" != "macos" ]; then
        install_xharness
    fi
}

if [ $# -lt 4 ]; then
    usage
    exit 1
fi

cbl_version=$1
dataset_version=$2
platform=$3
sgw_version=$4
private_key_path=""
SETUP_ONLY=false

# Parse optional arguments
for arg in "$@"; do
    if [ "$arg" = "--setup-only" ]; then
        SETUP_ONLY=true
    fi
done

if [ $# -gt 4 ]; then
    # Check if 5th argument is --setup-only
    if [ "$5" != "--setup-only" ]; then
        private_key_path=$5
    fi
fi

prepare_dotnet

create_venv venv
source venv/bin/activate
pip install -r $AWS_ENVIRONMENT_DIR/requirements.txt
if [ -n "$private_key_path" ]; then
    python3 $SCRIPT_DIR/setup_test.py $platform $cbl_version $dataset_version $sgw_version --private_key $private_key_path
else
    python3 $SCRIPT_DIR/setup_test.py $platform $cbl_version $dataset_version $sgw_version
fi
deactivate

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

pushd $QE_TESTS_DIR
create_venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest -v --no-header -W ignore::DeprecationWarning --config config.json
deactivate