#!/bin/bash
# Build the Android test server, deploy it, and run the tests

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -eu

BUILD_TOOLS_VERSION='34.0.0'
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
export PATH="/opt/homebrew/opt/coreutils/libexec/gnubin:/opt/homebrew/bin:$PATH"
source $SCRIPT_DIR/../../shared/config.sh

SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
if [ -z "${SDK_ROOT}" ]; then
    echo "ANDROID_HOME or ANDROID_SDK_ROOT must be set"
    exit 1
fi

export ANDROID_HOME="${SDK_ROOT}"
export ANDROID_SDK_ROOT="${SDK_ROOT}"

function resolve_sdkmanager() {
    local candidates=(
        "${SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager"
        "${SDK_ROOT}/cmdline-tools/bin/sdkmanager"
        "${SDK_ROOT}/tools/bin/sdkmanager"
    )

    for p in "${candidates[@]}"; do
        if [ -x "${p}" ]; then
            echo "${p}"
            return 0
        fi
    done

    if command -v sdkmanager >/dev/null 2>&1; then
        command -v sdkmanager
        return 0
    fi

    return 1
}

function bootstrap_cmdline_tools() {
    local url="${ANDROID_CMDLINE_TOOLS_URL:-https://dl.google.com/android/repository/commandlinetools-mac-11076708_latest.zip}"
    local tmp_dir
    tmp_dir="$(mktemp -d)"

    mkdir -p "${SDK_ROOT}/cmdline-tools"
    echo "Android SDK command-line tools not found; downloading to bootstrap sdkmanager..."
    curl -fL "${url}" -o "${tmp_dir}/commandlinetools.zip"
    unzip -q "${tmp_dir}/commandlinetools.zip" -d "${tmp_dir}/unzipped"

    rm -rf "${SDK_ROOT}/cmdline-tools/latest"
    mkdir -p "${SDK_ROOT}/cmdline-tools/latest"

    if [ -d "${tmp_dir}/unzipped/cmdline-tools" ]; then
        mv "${tmp_dir}/unzipped/cmdline-tools/"* "${SDK_ROOT}/cmdline-tools/latest/"
    else
        mv "${tmp_dir}/unzipped/"* "${SDK_ROOT}/cmdline-tools/latest/"
    fi

    rm -rf "${tmp_dir}"
}

function usage() {
    echo "Usage: $0 <cbl_version> <sg version> [private key path] [--setup-only]"
    echo "  --setup-only: Only build test server and setup backend, skip test execution"
    exit 1
}

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ] ; then usage; fi

CBL_VERSION="$1"
if [ -z "$CBL_VERSION" ]; then usage; fi

SG_VERSION="$2"
if [ -z "$SG_VERSION" ]; then usage; fi

SETUP_ONLY=false

# Check for --setup-only flag
for arg in "$@"; do
    if [ "$arg" = "--setup-only" ]; then
        SETUP_ONLY=true
        break
    fi
done

STATUS=0

echo "Install Android SDK"
SDK_MGR="$(resolve_sdkmanager || true)"
if [ -z "${SDK_MGR}" ]; then
    bootstrap_cmdline_tools
    SDK_MGR="$(resolve_sdkmanager)"
fi

yes | "${SDK_MGR}" --channel=1 --licenses
"${SDK_MGR}" --channel=1 --install "build-tools;${BUILD_TOOLS_VERSION}"
PATH="${PATH}:$ANDROID_HOME/platform-tools"

echo "Setup backend..."

create_venv venv
source venv/bin/activate
pip install -r $AWS_ENVIRONMENT_DIR/requirements.txt
python3 $SCRIPT_DIR/setup_test.py $CBL_VERSION $SG_VERSION
deactivate

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

echo "Start logcat"
pushd $SCRIPT_DIR
python3 logcat.py &
echo $! > logcat.pid

# Run Tests
echo "Run tests..."
pushd $QE_TESTS_DIR > /dev/null
create_venv venv
source venv/bin/activate
pip install -r requirements.txt
adb shell input keyevent KEYCODE_WAKEUP
pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json --dataset-version 3.2 -m cbl
deactivate
popd > /dev/null
