#!/bin/bash -e

function usage() {
    echo "Usage: $0 <binary type: all | simulator | device> <edition: enterprise | community> <version> [build num]"
    exit 1
}

if [ "$#" -lt 3 ]; then
    usage
fi

BIN_TYPE=${1}
EDITION=${2}
VERSION=${3}
BLD_NUM=${4}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

BUILD_OUT_DIR="${SCRIPT_DIR}/../build"
PROJECT_DIR="${SCRIPT_DIR}/.."
BUILD_SIMULATOR_DIR="${PROJECT_DIR}/build_simulator"
BUILD_DEVICE_DIR="${PROJECT_DIR}/build_device"

# Download CBL:
if [ -z "$BLD_NUM" ]
then
    ${SCRIPT_DIR}/download_cbl.sh ${EDITION} ${VERSION}
else
    ${SCRIPT_DIR}/download_cbl.sh ${EDITION} ${VERSION} ${BLD_NUM}
fi

# Go to iOS project directory:
pushd "${PROJECT_DIR}" > /dev/null

# Build and Copy Artifact
rm -rf "${BUILD_OUT_DIR}"
mkdir -p "${BUILD_OUT_DIR}"

set -o pipefail # Get xcpretty to report failures
if [ "${BIN_TYPE}" != "device" ]
then
    xcodebuild -scheme TestServer -sdk iphonesimulator -configuration Release -derivedDataPath "${BUILD_SIMULATOR_DIR}"
    cp -r "${BUILD_SIMULATOR_DIR}/Build/Products/Release-iphonesimulator/TestServer-iOS.app" "${BUILD_OUT_DIR}/TestServer-iOS-Simulator.app"
    echo ""
fi

if [ "${BIN_TYPE}" != "simulator" ]
then
    xcodebuild -scheme TestServer -sdk iphoneos -configuration Release -derivedDataPath "${BUILD_DEVICE_DIR}" -allowProvisioningUpdates
    cp -r "${BUILD_DEVICE_DIR}/Build/Products/Release-iphoneos/TestServer-iOS.app" "${BUILD_OUT_DIR}"
fi

rm -rf "${BUILD_SIMULATOR_DIR}"
rm -rf "${BUILD_DEVICE_DIR}"

popd > /dev/null