#!/bin/bash -e

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
source "$SCRIPT_DIR/../../shared/config.sh"

DOTNET_ENV_NAME="10.0"
XHARNESS_VERSION="10.0.0-prerelease*"
XHARNESS_SOURCE="https://pkgs.dev.azure.com/dnceng/public/_packaging/dotnet-eng/nuget/v3/index.json"

function usage() {
  echo "Usage: $0 <cbl_version[-build]> <platform> <sgw_version> [--es-version VERSION] [--dataset-version VERSION] [--test-filter EXPR] [--setup-only]"
  echo "  cbl_version: x.y.z for the latest build, or x.y.z-build for a specific one"
  echo "  platform: The .NET platform to test (macos, ios, android)"
  echo "  sgw_version: Version of Sync Gateway to download and use"
  echo "  --dataset-version: Version of CBL dataset to use (default: 4.0)"
  echo "  --es-version: Edge Server version (default: the latest release)"
  echo "  --test-filter: An optional pytest -k filter expression (disables result upload)"
  echo "  --setup-only: Only build test server and setup backend, skip test execution"
}

function prepare_dotnet() {
  # MAUI is installed by dotnetenv as part of the server build instead.
  uv run dotnetenv install "$DOTNET_ENV_NAME"
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
shift 3

SETUP_ONLY=false
DATASET_VERSION="4.0"
TEST_FILTER=""
ES_VERSION=""

# Parse optional arguments
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dataset-version)
      DATASET_VERSION="$2"
      shift 2
      ;;
    --es-version)
      ES_VERSION="$2"
      shift 2
      ;;
    --test-filter)
      TEST_FILTER="$2"
      shift 2
      ;;
    --setup-only)
      SETUP_ONLY=true
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ "$(uname)" == "Darwin" ]]; then
  export MD_APPLE_SDK_ROOT="/$(echo "$(xcode-select -p)" | cut -d'/' -f2-3)"
fi

prepare_dotnet

uv run "$SCRIPT_DIR/setup_test.py" "$platform" "$cbl_version" "$sgw_version" ${ES_VERSION:+--es-version "$ES_VERSION"}

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
  echo "Setup completed. Exiting due to --setup-only flag."
  exit 0
fi

pushd "$FUNCTIONAL_TESTS_DIR" >/dev/null
rm -rf http_log testserver.log

# Every test that needs a test server. Tests whose other min_* markers this
# topology can't satisfy are skipped by the required_topology plugin.
PYTEST_ARGS=(
  -v --no-header -W ignore::DeprecationWarning
  --config config.json
  --dataset-version "$DATASET_VERSION"
  -m min_test_servers
)
if [ -n "$TEST_FILTER" ]; then
  PYTEST_ARGS+=(-k "$TEST_FILTER" --no-result-upload)
fi

uv run pytest "${PYTEST_ARGS[@]}"
