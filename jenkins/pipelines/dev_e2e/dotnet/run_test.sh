#!/bin/bash -e

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../shared/config.sh

function usage() {
    echo "Usage: $0 <version> <platform> <sgw_version> [dataset-version]"
    echo "version: CBL version (e.g. 3.2.1-2)"
    echo "platform: The .NET platform to build (e.g. ios)"
    echo "sgw_version: Version of Sync Gateway to download and use"
    echo "dataset-version: Version of CBL dataset to use (default: 4.0)"
}

function prepare_dotnet() {
    # This used to install maui but that's too messy here since it constantly changes
    # the version of Xcode needed.  This is handled now as part of the server build instead.
    source $SCRIPT_DIR/prepare_env.sh
    install_dotnet "$DOTNET_SDK_VERSION"
    if [ "$platform" != "macos" ]; then
        install_xharness
    fi
}

if [ $# -lt 3 ]; then
    usage
    exit 1
fi

cbl_version=$1
platform=$2
sgw_version=$3
dataset_version=${4:-"4.0"}

if [[ "$(uname)" == "Darwin" ]]; then
    export MD_APPLE_SDK_ROOT="/$(echo "$(xcode-select -p)" | cut -d'/' -f2-3)"
fi

prepare_dotnet

uv run $SCRIPT_DIR/setup_test.py $platform $cbl_version $sgw_version

pushd $DEV_E2E_TESTS_DIR
uv run pytest -v --no-header --config config.json --dataset-version $dataset_version
