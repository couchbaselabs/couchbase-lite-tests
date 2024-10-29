#!/bin/bash
# Build the Android test server, deploy it, and run the tests

BUILD_TOOLS_VERSION='34.0.0'
SDK_MGR="${ANDROID_HOME}/cmdline-tools/latest/bin/sdkmanager --channel=1"

function usage() {
    echo "Usage: $0 <edition> <version> <build num>"
    exit 1
}

if [ "$#" -ne 3 ]; then usage; fi

EDITION="$1"
if [ -z "$EDITION" ]; then usage; fi

VERSION="$2"
if [ -z "$VERSION" ]; then usage; fi

BUILD_NUMBER="$3"
if [ -z "$BUILD_NUMBER" ]; then usage; fi


echo "Install Android SDK"
yes | ${SDK_MGR} --licenses > /dev/null 2>&1
${SDK_MGR} --install "build-tools;${BUILD_TOOLS_VERSION}"
PATH="${PATH}:$ANDROID_HOME/platform-tools"

# Get the Android device's IP address
ANDROID_IP=`adb shell ifconfig | perl -ne 'next unless /inet addr:([\d.]+) /; $ip = $1; next if $ip =~ /^127/; print "$1\n"'`

# Force the Couchbase Lite Android version
pushd servers/jak > /dev/null
echo "$VERSION" > cbl-version.txt

echo "Build Test Server"
cd android
adb uninstall com.couchbase.lite.android.mobiletest 2 >& 1 > /dev/null || true
./gradlew installRelease -PbuildNumber="${BUILD_NUMBER}"

echo "Start the Test Server"
adb shell am start -a android.intent.action.MAIN -n com.couchbase.lite.android.mobiletest/.MainActivity
popd > /dev/null

echo "Start Server/SGW"
pushd environment > /dev/null
./start_environment.py

popd > /dev/null
cp -f "jenkins/pipelines/android/config.android.json" tests

echo "Configure tests"
pushd tests
echo '    "test-servers": ["http://'"$ANDROID_IP"':8080"]' >> config.android.json
echo '}' >> config.android.json
cat config.android.json

echo "Start logcat"
python3.10 jenkins/pipelines/android/logcat.py 
echo $! > logcat.pid

echo "Running tests on device $ANDROID_SERIAL at $ANDROID_IP"
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

echo "Run tests"
adb shell input keyevent KEYCODE_WAKEUP
pytest -v --no-header -W ignore::DeprecationWarning --config config.android.json
