#!/bin/bash -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

function usage() {
    echo "Usage: stop_ios.sh device-id"
    echo "      device-id The UUID of the device to stop the test server on"
}

if [ $# -lt 1 ]; then
    usage
    exit 1
fi

pushd $SCRIPT_DIR

source $SCRIPT_DIR/prepare_env.sh
if [ ! -f  ios_pid.txt ]; then
    echo "Unable to find ios_pid.txt, was the app started using run_ios.sh?"
    exit 2
fi

pid=$(cat ios_pid.txt)
rm ios_pid.txt

banner "Stopping com.couchbase.dotnet.testserver ($pid) on device $1"
output=$($HOME/.dotnet/tools/xharness apple mlaunch -- --devname $1 --killdev $pid 2> /dev/null)