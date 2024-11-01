#!/bin/bash -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

function usage() {
    echo "Usage: run_ios.sh device-id"
    echo "      device-id The UUID of the device to run the test server on"
}

if [ $# -lt 1 ]; then
    usage
    exit 1
fi

pushd $SCRIPT_DIR/../../../servers/dotnet/testserver

source $SCRIPT_DIR/prepare_env.sh
app_location=$(find bin/Release/net8.0-ios/ -name "*.app")
if [ -z $app_location ]; then
    echo "Unable to find app to install, was it built?"
    exit 2
fi

banner "Installing $app_location to device $1"
$HOME/.dotnet/tools/xharness apple mlaunch -- --devname $1 --installdev $app_location
output=$($HOME/.dotnet/tools/xharness apple mlaunch -- --devname $1 --launchdev $app_location 2> /dev/null)
regex="pid ([0-9]+)"
if [[ $output =~ $regex ]]; then
    echo -n "${BASH_REMATCH[1]}" > $SCRIPT_DIR/ios_pid.txt
fi