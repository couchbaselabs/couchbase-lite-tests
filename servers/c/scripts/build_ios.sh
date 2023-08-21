#!/bin/bash -e

function usage() {
    echo "Usage: $0 <binary type: all | simulator | device> <edition: enterprise | community> <version> [build num]"
    exit 1
}

if [ "$#" -ne 3 ]; then
    usage
fi

BIN_TYPE=${1}
EDITION=${2}
VERSION=${3}
BLD_NUM=${4}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ASSETS_DIR="${SCRIPT_DIR}/../assets"

BUILD_DIR="${SCRIPT_DIR}/../build"
BUILD_BIN_DIR="${BUILD_DIR}/out/bin"
DOWNLOAD_DIR="${BUILD_DIR}/download"

IOS_DIR="${SCRIPT_DIR}/../platforms/ios"
FRAMEWORKS_DIR="${IOS_DIR}/Frameworks"
BUILD_SIMULATOR_DIR="${IOS_DIR}/build_simulator"
BUILD_DEVICE_DIR="${IOS_DIR}/build_device"

# Copy Assets
pushd "${ASSETS_DIR}" > /dev/null
cp -f ../../../dataset/*.cblite2.zip dataset
cp -f ../../../environment/sg/cert/cert.* cert
popd

# Download and Unzip CBL:
rm -rf "${DOWNLOAD_DIR}" 2> /dev/null
mkdir -p "${DOWNLOAD_DIR}"
pushd "${DOWNLOAD_DIR}" > /dev/null

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
cp -r CouchbaseLite.xcframework "${FRAMEWORKS_DIR}"
popd > /dev/null

# Go to iOS project directory:
pushd "${IOS_DIR}" > /dev/null

# Get vendor
pushd vendor > /dev/null
sh cmake.sh
popd > /dev/null

# Build and Copy Artifact
rm -rf "${BUILD_BIN_DIR}"
mkdir -p "${BUILD_BIN_DIR}"

set -o pipefail # Get xcpretty to report failures
if [ "${BIN_TYPE}" != "device" ]
then
    xcodebuild -scheme TestServer -sdk iphonesimulator -configuration Release -derivedDataPath "${BUILD_SIMULATOR_DIR}" | xcpretty
    cp -r "$BUILD_SIMULATOR_DIR/Build/Products/Release-iphonesimulator/TestServer.app" "${BUILD_BIN_DIR}/TestServer-Simulator.app"
fi

if [ "${BIN_TYPE}" != "simulator" ]
then
    xcodebuild -scheme TestServer -sdk iphoneos -configuration Release -derivedDataPath "${BUILD_DEVICE_DIR}" -allowProvisioningUpdates | xcpretty  
    cp -r "$BUILD_DEVICE_DIR/Build/Products/Release-iphoneos/TestServer.app" "${BUILD_BIN_DIR}"
fi

popd > /dev/null