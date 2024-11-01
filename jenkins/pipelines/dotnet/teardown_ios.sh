#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source $SCRIPT_DIR/test_common.sh
source $SCRIPT_DIR/prepare_env.sh

banner "Looking up connected iOS device"

ios_devices=$($HOME/.dotnet/tools/xharness apple device ios-device)
ios_device=$(echo $ios_devices | head -1)
echo "Found device $ios_device..."

banner "Shutdown Test Server for iOS"
$SCRIPT_DIR/stop_ios.sh $ios_device

banner "Shutdown Environment"
end_tests