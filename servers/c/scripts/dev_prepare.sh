#!/bin/bash -e

function usage() {
    echo "Usage: $0 <platform: macos | linux | ios | android> <edition: enterprise | community> <version> [build num]"
    exit 1
}

if [ "$#" -ne 3 ]; then
    usage
fi

PLATFORM=${1}
EDITION=${2}
VERSION=${3}
BLD_NUM=${4}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ASSETS_DIR="${SCRIPT_DIR}/../assets"
DOWNLOAD_DIR="${SCRIPT_DIR}/../download"
LIB_DIR="${SCRIPT_DIR}/../lib"

IOS_FRAMEWORKS_DIR="${SCRIPT_DIR}/../platforms/ios/Frameworks"
IOS_VENDOR_DIR="${SCRIPT_DIR}/../platforms/ios/vendor"
ANDROID_CPP_DIR="${SCRIPT_DIR}/../platforms/android/app/src/main/cpp"

# Copy Assets
pushd "${ASSETS_DIR}" > /dev/null
cp -f ../../../dataset/*.cblite2.zip dataset
cp -f ../../../environment/sg/cert/cert.* cert
popd

# Download and Unzip CBL:
rm -rf "${DOWNLOAD_DIR}" 2> /dev/null
mkdir -p "${DOWNLOAD_DIR}"
pushd "${DOWNLOAD_DIR}" > /dev/null

if [ ${PLATFORM} = "macos" ]
then
    if [ -z "$BLD_NUM" ]
    then
        ZIP_FILENAME=couchbase-lite-c-${EDITION}-${VERSION}-macos.zip
        curl -O https://packages.couchbase.com/releases/couchbase-lite-c/${VERSION}/${ZIP_FILENAME}
    else
        ZIP_FILENAME=couchbase-lite-c-${EDITION}-${VERSION}-${BLD_NUM}-macos.zip
        curl -O http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-c/${VERSION}/${BLD_NUM}/${ZIP_FILENAME}
    fi
    unzip ${ZIP_FILENAME}
    rm -rf "${LIB_DIR}/libcblite"
    cp -r "libcblite-${VERSION}" "${LIB_DIR}/libcblite"
fi

if [ ${PLATFORM} = "linux" ]
then
    OS_ARCH=`uname -m`
    if [ ${OS_ARCH} = "aarch64" ]
    then
        OS_ARCH="arm64"
    fi

    if [ -z "$BLD_NUM" ]
    then
        ZIP_FILENAME=couchbase-lite-c-${EDITION}-${VERSION}-linux-${OS_ARCH}.tar.gz
        curl -O https://packages.couchbase.com/releases/couchbase-lite-c/${VERSION}/${ZIP_FILENAME}
    else
        ZIP_FILENAME=couchbase-lite-c-${EDITION}-${VERSION}-${BLD_NUM}-linux-${OS_ARCH}.tar.gz
        curl -O http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-c/${VERSION}/${BLD_NUM}/${ZIP_FILENAME}
    fi
    tar xvf ${ZIP_FILENAME}
    rm -rf "${LIB_DIR}/libcblite"
    cp -r "libcblite-${VERSION}" "${LIB_DIR}/libcblite"
fi

if [ ${PLATFORM} = "ios" ]
then
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
    rm -rf "${IOS_FRAMEWORKS_DIR}/CouchbaseLite.xcframework"
    cp -r CouchbaseLite.xcframework "${IOS_FRAMEWORKS_DIR}"

    # Go to iOS vendor directory and get vendors
    pushd "${IOS_VENDOR_DIR}" > /dev/null
    sh cmake.sh
    popd > /dev/null
fi

if [ ${PLATFORM} = "android" ]
then
    if [ -z "${BLD_NUM}" ]
    then
        ZIP_FILENAME=couchbase-lite-c-${EDITION}-${VERSION}-android.zip
        curl -O https://packages.couchbase.com/releases/couchbase-lite-c/${VERSION}/${ZIP_FILENAME}
    else
        ZIP_FILENAME=couchbase-lite-c-${EDITION}-${VERSION}-${BLD_NUM}-android.zip
        curl -O http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-c/${VERSION}/${BLD_NUM}/${ZIP_FILENAME}
    fi
    unzip ${ZIP_FILENAME}
    rm -rf "${ANDROID_CPP_DIR}/lib/libcblite"
    cp -r libcblite-${VERSION} "${ANDROID_CPP_DIR}/lib/libcblite"
fi

popd > /dev/null

rm -rf "${DOWNLOAD_DIR}" 2> /dev/null