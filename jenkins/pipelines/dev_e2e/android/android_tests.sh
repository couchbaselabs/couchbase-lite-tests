#!/bin/bash
# Build the Android test server, deploy it, and run the tests

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -eu # No pipefail because piping yes always "fails" with SIGPIPE

BUILD_TOOLS_VERSION='34.0.0'
SDK_MGR="${ANDROID_HOME}/cmdline-tools/latest/bin/sdkmanager"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

function usage() {
    echo "Usage: $0 <cbl_version> <dataset version> <sg version> [private key path]"
    exit 1
}

if [ "$#" -lt 3 ] | [ "$#" -gt 4 ] ; then usage; fi

CBL_VERSION="$1"
if [ -z "$CBL_VERSION" ]; then usage; fi

DATASET_VERSION="$2"
if [ -z "$DATASET_VERSION" ]; then usage; fi

SG_VERSION="$3"
if [ -z "$SG_VERSION" ]; then usage; fi

private_key_path="$4"
STATUS=0

echo "Install Android SDK"
yes | ${SDK_MGR} --channel=1 --licenses > /dev/null 2>&1
${SDK_MGR} --channel=1 --install "build-tools;${BUILD_TOOLS_VERSION}"
PATH="${PATH}:$ANDROID_HOME/platform-tools"

create_venv venv
source venv/bin/activate
pip install -r $AWS_ENVIRONMENT_DIR/requirements.txt
if [ -n "$private_key_path" ]; then
    python3 $SCRIPT_DIR/setup_test.py $CBL_VERSION $DATASET_VERSION $SG_VERSION --private_key $private_key_path
else
    python3 $SCRIPT_DIR/setup_test.py $CBL_VERSION $DATASET_VERSION $SG_VERSION
fi
deactivate

echo "Start logcat"
pushd $SCRIPT_DIR
python3 logcat.py &
echo $! > logcat.pid

pushd $DEV_E2E_TESTS_DIR > /dev/null
rm -rf venv http_log testserver.log
create_venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "Run the tests"
adb shell input keyevent KEYCODE_WAKEUP
pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json
