#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source $SCRIPT_DIR/test_common.sh

if [ $# -lt 3 ]; then
    usage
    exit 1
fi

cbl_version=$1
cbl_build=$2
dataset_version=$3
sgw_url="$4"

prepare_dotnet $dataset_version

banner "Looking up connected iOS device"
if [ -f $SCRIPT_DIR/ios_device.txt ]; then 
    #Workaround for https://github.com/xamarin/xamarin-macios/issues/21564
    ios_device=$(cat $SCRIPT_DIR/ios_device.txt)
else
    ios_devices=$($HOME/.dotnet/tools/xharness apple device ios-device)
    ios_device=$(echo $ios_devices | head -1)
fi

echo "Found device $ios_device..."

modify_package $cbl_version $cbl_build
$SCRIPT_DIR/build_ios.sh
$SCRIPT_DIR/run_ios.sh $ios_device
$SCRIPT_DIR/../shared/setup_backend.sh $sgw_url

banner "Resolving Test Server IP"
test_server_ip=$(dns-sd -t 1 -B _testserver._tcp | tail -1 | awk '{gsub(/-/, ".",  $7)} {print $7}')
if [ "$test_server_ip" == "" ]; then
    test_server_ip=$IOS_TEST_SERVER_IP
fi

if [ "$test_server_ip" == "" ]; then
    echo "Failed to find iOS test server..."
    exit 2
else
    echo "Resolved to $test_server_ip!"
fi

my_ip=$(ifconfig en0 | grep "inet " | awk '{print $2}')
echo "Detected TDK client IP as $my_ip"
begin_tests $test_server_ip $my_ip
