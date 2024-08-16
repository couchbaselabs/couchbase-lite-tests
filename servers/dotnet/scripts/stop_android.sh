#!/bin/bash -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

function usage() {
    echo "Usage: stop_android.sh device-id"
    echo "      device-id The device to stop the test server on"
}

if [ $# -lt 1 ]; then
    usage
    exit 1
fi

source $SCRIPT_DIR/prepare_env.sh

banner "Stopping com.couchbase.dotnet.testserver"

$HOME/.dotnet/tools/xharness android adb -- -s $1 shell am force-stop com.couchbase.dotnet.testserver