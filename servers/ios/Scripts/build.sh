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

BUILD_OUT_DIR="${SCRIPT_DIR}/../build"
PROJECT_DIR="${SCRIPT_DIR}/.."
BUILD_SIMULATOR_DIR="${PROJECT_DIR}/build_simulator"
BUILD_DEVICE_DIR="${PROJECT_DIR}/build_device"

# Prepare Environment:
"${SCRIPT_DIR}"/prepare_env.sh ${DATASET_VERSION}

# Download CBL:
"${SCRIPT_DIR}"/download_cbl.sh ${EDITION} ${VERSION} ${BLD_NUM}

# Go to iOS project directory:
pushd "${PROJECT_DIR}" > /dev/null

# Build and Copy Artifact
rm -rf "${BUILD_OUT_DIR}"
mkdir -p "${BUILD_OUT_DIR}"

# xcpretty setup:
set -o pipefail 
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

if [ "${BIN_TYPE}" != "device" ]
then
    xcodebuild -scheme TestServer -sdk iphonesimulator -configuration Release -derivedDataPath "${BUILD_SIMULATOR_DIR}" | xcpretty
    cp -r "${BUILD_SIMULATOR_DIR}/Build/Products/Release-iphonesimulator/TestServer-iOS.app" "${BUILD_OUT_DIR}/TestServer-iOS-Simulator.app"
    echo ""
fi

if [ "${BIN_TYPE}" != "simulator" ]
then
    xcodebuild -scheme TestServer -sdk iphoneos -configuration Release -derivedDataPath "${BUILD_DEVICE_DIR}" -allowProvisioningUpdates | xcpretty
    cp -r "${BUILD_DEVICE_DIR}/Build/Products/Release-iphoneos/TestServer-iOS.app" "${BUILD_OUT_DIR}"
fi

rm -rf "${BUILD_SIMULATOR_DIR}"
rm -rf "${BUILD_DEVICE_DIR}"

popd > /dev/null