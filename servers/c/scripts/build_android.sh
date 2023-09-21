#!/bin/bash -e

function usage() {
    echo "Usage: $0 <abi: all | x86,armeabi-v7a,x86_64,arm64-v8a> <edition: enterprise | community> <version> [build num]"
    exit 1
}

if [ "$#" -lt 3 ]; then
    usage
fi

ABI=${1}
EDITION=${2}
VERSION=${3}
BLD_NUM=${4}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
BUILD_DIR="${SCRIPT_DIR}/../build"
BUILD_BIN_DIR="${BUILD_DIR}/out/bin"
DOWNLOAD_DIR="${BUILD_DIR}/download"

ANDROID_DIR="${SCRIPT_DIR}/../platforms/android"
ANDROID_CPP_DIR="${ANDROID_DIR}/app/src/main/cpp"

# Download CBL:
if [ -z "$BLD_NUM" ]
then
    ${SCRIPT_DIR}/download_cbl.sh android ${EDITION} ${VERSION}
else
    ${SCRIPT_DIR}/download_cbl.sh android ${EDITION} ${VERSION} ${BLD_NUM}
fi

# Build
pushd "$ANDROID_DIR" > /dev/null
mv local.properties local.properties.build.bak 2> /dev/null || true
echo "sdk.dir=${ANDROID_HOME}" > local.properties

if [ "${ABI}" == "all" ]
then
    ./gradlew assembleRelease
else
    ./gradlew assembleRelease -PabiFilters=${ABI}
fi

mv local.properties.build.bak local.properties 2> /dev/null || true

# Copy built artifacts
rm -rf "${BUILD_BIN_DIR}"
mkdir -p "${BUILD_BIN_DIR}"
cp ./app/build/outputs/apk/release/app-release.apk "${BUILD_BIN_DIR}"
popd > /dev/null
