#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source $SCRIPT_DIR/test_common.sh
source $SCRIPT_DIR/prepare_env.sh

banner "Looking up connected Android device"
android_device=$($HOME/.dotnet/tools/xharness android device)
if [ "$android_device" == "" ]; then
    echo "Failed to find Android device"
    exit 2
else
    echo "Found $android_device"
fi

banner "Shutdown Test Server for Android"
$SCRIPT_DIR/stop_android.sh $android_device

banner "Shutdown Environment"
end_tests