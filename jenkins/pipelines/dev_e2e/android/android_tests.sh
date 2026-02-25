#!/bin/bash
# Build the Android test server, deploy it, and run the tests

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -eu # No pipefail because piping yes always "fails" with SIGPIPE

BUILD_TOOLS_VERSION='34.0.0'
SDK_MGR="${ANDROID_HOME}/cmdline-tools/latest/bin/sdkmanager"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

function usage() {
    echo "Usage: $0 <cbl_version> <sg version>"
    exit 1
}

if [ "$#" -lt 2 ] ; then usage; fi

CBL_VERSION="$1"
if [ -z "$CBL_VERSION" ]; then usage; fi

SG_VERSION="$2"
if [ -z "$SG_VERSION" ]; then usage; fi
DATASET_VERSION=${3:-"4.0"}

STATUS=0

echo "Install Android SDK"
yes | ${SDK_MGR} --channel=1 --licenses > /dev/null 2>&1
${SDK_MGR} --channel=1 --install "build-tools;${BUILD_TOOLS_VERSION}"
PATH="${PATH}:$ANDROID_HOME/platform-tools"

uv run --group orchestrator $SCRIPT_DIR/setup_test.py $CBL_VERSION $SG_VERSION

echo "Start logcat"
pushd $SCRIPT_DIR
python3 logcat.py &
echo $! > logcat.pid

pushd $DEV_E2E_TESTS_DIR > /dev/null
rm -rf http_log testserver.log

echo "Run the tests"
# To re-enable this, this script needs to become aware of the
# serial number of the device, which is not currently passed
#adb shell input keyevent KEYCODE_WAKEUP
uv run pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json --dataset-version $DATASET_VERSION || STATUS=$?
