#!/bin/bash -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

function usage() {
    echo "Usage: run_android.sh device-id"
    echo "      device-id The device to run the test server on"
}

if [ $# -lt 1 ]; then
    usage
    exit 1
fi

pushd $SCRIPT_DIR/../testserver

source $SCRIPT_DIR/prepare_env.sh
apk_location=$(find bin/Release/net8.0-android/publish -name "*.apk")
if [ -z $apk_location ]; then
    echo "Unable to find APK to install, was it built?"
    exit 2
fi

echo "Installing $apk_location to device $1..."
$HOME/.dotnet/tools/xharness android install -a $apk_location -p com.couchbase.dotnet.testserver -o out --device-id $1
$HOME/.dotnet/tools/xharness android adb -- -s $1 shell am start com.couchbase.dotnet.testserver/com.couchbase.dotnet.testserver.MainActivity