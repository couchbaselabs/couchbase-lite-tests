#!/bin/bash
# Build the Android test server, deploy it, and run the tests

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -eu

BUILD_TOOLS_VERSION='34.0.0'
SDK_MGR="${ANDROID_HOME}/cmdline-tools/latest/bin/sdkmanager"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

function usage() {
    echo "Usage: $0 <cbl_version> <sg version> [private key path] [--setup-only]"
    echo "  --setup-only: Only build test server and setup backend, skip test execution"
    exit 1
}

if [ "$#" -lt 2 ] || [ "$#" -gt 4 ] ; then usage; fi

CBL_VERSION="$1"
if [ -z "$CBL_VERSION" ]; then usage; fi

SG_VERSION="$2"
if [ -z "$SG_VERSION" ]; then usage; fi

private_key_path="$3"
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
yes | ${SDK_MGR} --channel=1 --licenses
${SDK_MGR} --channel=1 --install "build-tools;${BUILD_TOOLS_VERSION}"
PATH="${PATH}:$ANDROID_HOME/platform-tools"

echo "Setup backend..."

create_venv venv
source venv/bin/activate
pip install -r $AWS_ENVIRONMENT_DIR/requirements.txt
if [ -n "$private_key_path" ]; then
    python3 $SCRIPT_DIR/setup_test.py $CBL_VERSION $SG_VERSION --private_key $private_key_path
else
    python3 $SCRIPT_DIR/setup_test.py $CBL_VERSION $SG_VERSION
fi
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
pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json -m cbl
deactivate
popd > /dev/null
