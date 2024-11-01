#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source $SCRIPT_DIR/test_common.sh

sgw_url="$4"
if [ $# -lt 3 ]; then
    usage
    exit 1
fi

prepare_dotnet

modify_package $2 $3
$SCRIPT_DIR/build_android.sh

banner "Looking up connected Android device"
android_device=$($HOME/.dotnet/tools/xharness android device)
if [ "$android_device" == "" ]; then
    echo "Failed to find Android device"
    exit 2
else
    echo "Found $android_device"
fi

banner "Resolving Test Server IP"
test_server_ip=$($HOME/.dotnet/tools/xharness android adb -- shell ifconfig wlan0 | grep "inet addr" | awk '{print substr($2, 6)}')
if [ "$test_server_ip" == "" ]; then
    echo "Failed to find Android test server..."
    exit 2
else
    echo "Resolved to $test_server_ip!"
fi

my_ip=$(ifconfig en0 | grep "inet " | awk '{print $2}')
echo "Detected TDK client IP as $my_ip"

$SCRIPT_DIR/run_android.sh $android_device
$SCRIPT_DIR/../shared/setup_backend.sh $sgw_url

begin_tests $test_server_ip $my_ip