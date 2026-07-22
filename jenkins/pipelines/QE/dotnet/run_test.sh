#!/bin/bash -e

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR/../../shared/config.sh"

DOTNET_ENV_NAME="10.0"
XHARNESS_VERSION="10.0.0-prerelease*"
XHARNESS_SOURCE="https://pkgs.dev.azure.com/dnceng/public/_packaging/dotnet-eng/nuget/v3/index.json"

function usage() {
    echo "Usage: $0 <version> <platform> <sgw_version> [dataset-version] [--setup-only]"
    echo "version: CBL version (e.g. 3.2.1-2)"
    echo "platform: The .NET platform to build (e.g. ios)"
    echo "sgw_version: Version of Sync Gateway to download and use"
    echo "dataset-version: Version of CBL dataset to use (default: 4.0)"
    echo "  --setup-only: Only build test server and setup backend, skip test execution"
}

function prepare_dotnet() {
    source "$SCRIPT_DIR/prepare_env.sh"
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

SETUP_ONLY=false
DATASET_VERSION="4.0"

# Parse optional arguments
for arg in "${@:4}"; do
    case "$arg" in
        --setup-only)
            SETUP_ONLY=true
            ;;
        *)
            DATASET_VERSION="$arg"
            ;;
    esac
done

prepare_dotnet

uv run "$SCRIPT_DIR/setup_test.py" "$platform" "$cbl_version" "$sgw_version"

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

pushd "$QE_TESTS_DIR"

export DEVELOPER_DIR="/Applications/Xcode-$DOTNET_XCODE_VERSION.app/"
uv run pytest -v --no-header -W ignore::DeprecationWarning \
    --config config.json \
    --dataset-version "$DATASET_VERSION" \
    -m cbl