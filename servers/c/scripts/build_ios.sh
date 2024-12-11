#!/bin/bash -e

function usage() {
    echo "Usage: $0 <binary type: all | simulator | device> <edition: enterprise | community> <cbl-version> <cbl-build-num> <dataset-version>"
    exit 1
}

if [ "$#" -lt 5 ]; then
    usage
fi

BIN_TYPE=${1}
EDITION=${2}
VERSION=${3}
BLD_NUM=${4}
DATASET_VERSION=${5}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

BUILD_DIR="${SCRIPT_DIR}/../build"
BUILD_BIN_DIR="${BUILD_DIR}/out/bin"

IOS_DIR="${SCRIPT_DIR}/../platforms/ios"
BUILD_SIMULATOR_DIR="${IOS_DIR}/build_simulator"
BUILD_DEVICE_DIR="${IOS_DIR}/build_device"

# Prepare Environment:
"${SCRIPT_DIR}"/prepare_env.sh ${DATASET_VERSION}

# Download CBL:
"${SCRIPT_DIR}"/download_cbl.sh ios ${EDITION} ${VERSION} ${BLD_NUM}

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