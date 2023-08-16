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
BUILD_DIR="${SCRIPT_DIR}/../build"
BUILD_BIN_DIR="${BUILD_DIR}/out/bin"
DOWNLOAD_DIR="${BUILD_DIR}/download"

ANDROID_DIR="${SCRIPT_DIR}/../platforms/android"
ANDROID_CPP_DIR="${ANDROID_DIR}/app/src/main/cpp"

# Copy Assets
pushd "${ASSETS_DIR}" > /dev/null
cp -f ../../../dataset/*.cblite2.zip dataset
cp -f ../../../environment/sg/cert/cert.* cert
popd

# Download and Unzip CBL:
rm -rf "${DOWNLOAD_DIR}" 2> /dev/null
mkdir -p "${DOWNLOAD_DIR}"
pushd "${DOWNLOAD_DIR}" > /dev/null

if [ -z "${BLD_NUM}" ]
then
    ZIP_FILENAME=couchbase-lite-c-${EDITION}-${VERSION}-android.zip
    curl -O https://packages.couchbase.com/releases/couchbase-lite-c/${VERSION}/${ZIP_FILENAME}
else
    ZIP_FILENAME=couchbase-lite-c-${EDITION}-${VERSION}-${BLD_NUM}-android.zip
    curl -O http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-c/${VERSION}/${BLD_NUM}/${ZIP_FILENAME}
fi
unzip ${ZIP_FILENAME}
rm ${ZIP_FILENAME}

rm -rf "${ANDROID_CPP_DIR}/lib/libcblite"
cp -r "libcblite-${VERSION}" "${ANDROID_CPP_DIR}/lib/libcblite"
popd > /dev/null

# Build
pushd "$ANDROID_DIR" > /dev/null
mv local.properties local.properties.build.bak 2> /dev/null || true
echo "sdk.dir=${ANDROID_HOME}" > local.properties
./gradlew assembleRelease
mv local.properties.build.bak local.properties 2> /dev/null || true

# Copy built artifacts
rm -rf "${BUILD_BIN_DIR}"
mkdir -p "${BUILD_BIN_DIR}"
cp ./app/build/outputs/apk/release/app-release.apk "${BUILD_BIN_DIR}"
popd > /dev/null
