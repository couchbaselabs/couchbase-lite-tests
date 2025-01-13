#!/bin/bash
# Build the Android test server, deploy it, and run the tests

BUILD_TOOLS_VERSION='34.0.0'
SDK_MGR="${ANDROID_HOME}/cmdline-tools/latest/bin/sdkmanager --channel=1"

function usage() {
    echo "Usage: $0 <cbl_version> <dataset version> [<sg url>]"
    exit 1
}

if [ "$#" -lt 2 ] | [ "$#" -gt 3 ] ; then usage; fi

CBL_VERSION="$1"
if [ -z "$CBL_VERSION" ]; then usage; fi

DATASET_VERSION="$2"
if [ -z "$DATASET_VERSION" ]; then usage; fi

SG_URL="$3"

$STATUS=0


echo "Install Android SDK"
yes | ${SDK_MGR} --licenses > /dev/null 2>&1
${SDK_MGR} --install "build-tools;${BUILD_TOOLS_VERSION}"
PATH="${PATH}:$ANDROID_HOME/platform-tools"

# Get the Android device's IP address
ANDROID_IP=$(adb shell ifconfig | perl -ne 'next unless /inet addr:([\d.]+) /; $ip = $1; next if $ip =~ /^127/; print "$1\n"')

pushd servers/jak > /dev/null

# Set up assets directory
etc/jenkins/copy_assets.sh ../../dataset/server assets

cd android

echo "Build the Test Server"
adb uninstall com.couchbase.lite.android.mobiletest 2 >& 1 > /dev/null || true
rm -rf app/build
./gradlew installRelease -PcblVersion="${CBL_VERSION}" -PdatasetVersion="${DATASET_VERSION}"

echo "Start the Test Server"
adb shell am start -a android.intent.action.MAIN -n com.couchbase.lite.android.mobiletest/.MainActivity
popd > /dev/null

echo "Start the environment"
jenkins/pipelines/shared/setup_backend.sh "${SG_URL}"

echo "Configure the tests"
rm -rf tests/config_android.json
cp -f "jenkins/pipelines/android/config_android.json" tests
pushd tests
echo '    "test-servers": ["http://'"$ANDROID_IP"':8080"]' >> config_android.json
echo '}' >> config_android.json
cat config_android.json

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

