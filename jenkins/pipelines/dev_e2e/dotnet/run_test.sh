#!/bin/bash -e

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../shared/config.sh

DOTNET_ENV_NAME="10.0"
XHARNESS_VERSION="10.0.0-prerelease*"
XHARNESS_SOURCE="https://pkgs.dev.azure.com/dnceng/public/_packaging/dotnet-eng/nuget/v3/index.json"

function usage() {
    echo "Usage: $0 <version> <platform> <sgw_version> [dataset-version]"
    echo "version: CBL version (e.g. 3.2.1-2)"
    echo "platform: The .NET platform to build (e.g. ios)"
    echo "sgw_version: Version of Sync Gateway to download and use"
    echo "dataset-version: Version of CBL dataset to use (default: 4.0)"
}

function prepare_dotnet() {
    # MAUI is installed by dotnetenv as part of the server build instead.
    uv run --group dotnet-build dotnetenv install "$DOTNET_ENV_NAME"
    if [ "$platform" != "macos" ]; then
        # XHarness is shared, machine-wide infra (swift_ios/c_ios also rely on
        # it), so install it at the default global tool location, not inside
        # dotnetenv's isolated environment directory.
        local dotnet_exe="$HOME/.dotnet${DOTNET_ENV_NAME%%.*}/dotnet"
        if ! "$dotnet_exe" tool list --global | grep -qi microsoft.dotnet.xharness.cli; then
            "$dotnet_exe" tool install --global Microsoft.DotNet.XHarness.CLI \
                --version "$XHARNESS_VERSION" --add-source "$XHARNESS_SOURCE"
        fi
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
uv run pytest -v --no-header --config config.json --dataset-version $dataset_version cbl/
