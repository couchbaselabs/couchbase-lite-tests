#!/bin/bash
# Build the Android test server, deploy it, and run the tests

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -eu

BUILD_TOOLS_VERSION='34.0.0'
SDK_MGR="${ANDROID_HOME}/cmdline-tools/latest/bin/sdkmanager"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
export PATH="/opt/homebrew/opt/coreutils/libexec/gnubin:/opt/homebrew/bin:$PATH"
source $SCRIPT_DIR/../../shared/config.sh

function usage() {
    echo "Usage: $0 <cbl_version> <sg_version> [dataset_version] [--setup-only]"
    echo "  dataset_version: Version of CBL dataset to use (default: 4.0)"
    echo "  --setup-only: Only build test server and setup backend, skip test execution"
    exit 1
}

# Allow up to 4 args now (2 required + dataset + flag)
if [ "$#" -lt 2 ] || [ "$#" -gt 4 ] ; then usage; fi

CBL_VERSION="$1"
if [ -z "$CBL_VERSION" ]; then usage; fi

SG_VERSION="$2"
if [ -z "$SG_VERSION" ]; then usage; fi

DATASET_VERSION="4.0"
SETUP_ONLY=false

# Parse optional args (starting from 3rd)
for arg in "${@:3}"; do
    case "$arg" in
        --setup-only)
            SETUP_ONLY=true
            ;;
        *)
            DATASET_VERSION="$arg"
            ;;
    esac
done

echo "Install Android SDK"
yes | "$SDK_MGR" --channel=1 --licenses
"$SDK_MGR" --channel=1 --install "build-tools;${BUILD_TOOLS_VERSION}"
PATH="${PATH}:$ANDROID_HOME/platform-tools"

echo "Setup backend..."
uv run $SCRIPT_DIR/setup_test.py "$CBL_VERSION" "$SG_VERSION"

if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

echo "Start logcat"
pushd $SCRIPT_DIR
python3 logcat.py &
echo $! > logcat.pid

echo "Run tests..."
pushd $QE_TESTS_DIR > /dev/null
adb shell input keyevent KEYCODE_WAKEUP
uv run pytest --maxfail=7 -W ignore::DeprecationWarning \
    --config config.json \
    --dataset-version "$DATASET_VERSION" \
    -m cbl