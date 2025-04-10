#!/bin/bash
# Build the Android test server, deploy it, and run the tests

BUILD_TOOLS_VERSION='34.0.0'
SDK_MGR="${ANDROID_HOME}/cmdline-tools/latest/bin/sdkmanager --channel=1"

function usage() {
    echo "Usage: $0 <cbl_version> <dataset version> <sg version>"
    exit 1
}

if [ "$#" -lt 2 ] | [ "$#" -gt 3 ] ; then usage; fi

CBL_VERSION="$1"
if [ -z "$CBL_VERSION" ]; then usage; fi

DATASET_VERSION="$2"
if [ -z "$DATASET_VERSION" ]; then usage; fi

SG_VERSION="$3"

$STATUS=0

echo "Install Android SDK"
yes | ${SDK_MGR} --licenses > /dev/null 2>&1
${SDK_MGR} --install "build-tools;${BUILD_TOOLS_VERSION}"
PATH="${PATH}:$ANDROID_HOME/platform-tools"

python3.10 -m venv venv
source venv/bin/activate
pip install -r $SCRIPT_DIR/../../../environment/aws/requirements.txt
if [ -n "$private_key_path" ]; then
    python3.10 $SCRIPT_DIR/setup_test.py $CBL_VERSION $DATASET_VERSION $SG_VERSION --private_key $private_key_path
else
    python3.10 $SCRIPT_DIR/setup_test.py $CBL_VERSION $DATASET_VERSION $SG_VERSION
fi
deactivate

rm -rf venv http_log testserver.log
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

echo "Start logcat"
python3.10 jenkins/pipelines/android/logcat.py 
echo $! > logcat.pid

echo "Run the tests"
adb shell input keyevent KEYCODE_WAKEUP
pytest --maxfail=7 -W ignore::DeprecationWarning --config config_android.json
$STATUS=$?

echo "Tests complete: $STATUS"
exit $STATUS

