#!/bin/bash -e

function usage() {
    echo "Usage: $0 <edition: enterprise | community> <version> [build num]"
    exit 1
}

if [ "$#" -ne 2 ]; then
    usage
fi

EDITION=${1}
VERSION=${2}
BLD_NUM=${3}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ASSETS_DIR="${SCRIPT_DIR}/../assets"
IOS_DIR="${SCRIPT_DIR}/../platforms/ios"
BUILD_SIMULATOR_DIR="${IOS_DIR}/build_simulator"
BUILD_DEVICE_DIR="${IOS_DIR}/build_device"

# Copy Assets
pushd "${ASSETS_DIR}" > /dev/null
cp -f ../../../dataset/*.cblite2.zip dataset
cp -f ../../../environment/sg/cert/cert.* cert
popd

# Go to iOS project directory:
pushd "${IOS_DIR}" > /dev/null

# Download and Unzip CBL:
pushd Frameworks > /dev/null
rm -rf CouchbaseLite.xcframework
rm -f *.txt

if [ -z "$BLD_NUM" ]
then
    ZIP_FILENAME=couchbase-lite-c-${EDITION}-${VERSION}-ios.zip
    curl -O https://packages.couchbase.com/releases/couchbase-lite-c/${VERSION}/${ZIP_FILENAME}
    echo "https://packages.couchbase.com/releases/couchbase-lite-c/${VERSION}/${ZIP_FILENAME}"
else
    ZIP_FILENAME=couchbase-lite-c-${EDITION}-${VERSION}-${BLD_NUM}-ios.zip
    curl -O http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-c/${VERSION}/${BLD_NUM}/${ZIP_FILENAME}
fi
unzip ${ZIP_FILENAME}
rm ${ZIP_FILENAME}
rm *.txt
popd > /dev/null

# Get vendor
pushd vendor > /dev/null
sh cmake.sh
popd > /dev/null

set -o pipefail # Get xcpretty to report failures
xcodebuild -scheme TestServer -sdk iphonesimulator -configuration Release -derivedDataPath "${BUILD_SIMULATOR_DIR}" | xcpretty
xcodebuild -scheme TestServer -sdk iphoneos -configuration Release -derivedDataPath "${BUILD_DEVICE_DIR}" -allowProvisioningUpdates | xcpretty

popd > /dev/null