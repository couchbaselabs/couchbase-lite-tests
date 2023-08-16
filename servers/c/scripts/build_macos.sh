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
BUILD_DIR=$SCRIPT_DIR/../build
DOWNLOAD_DIR=$BUILD_DIR/download

# Download and Unzip CBL:
rm -rf $DOWNLOAD_DIR 2> /dev/null
mkdir -p $DOWNLOAD_DIR
pushd $DOWNLOAD_DIR > /dev/null

if [ -z "$BLD_NUM" ]
then
    ZIP_FILENAME=couchbase-lite-c-${EDITION}-${VERSION}-macos.zip
    echo "$ZIP_FILENAME"
    curl -O https://packages.couchbase.com/releases/couchbase-lite-c/${VERSION}/${ZIP_FILENAME}
else
    ZIP_FILENAME=couchbase-lite-c-${EDITION}-${VERSION}-${BLD_NUM}-macos.zip
    curl -O http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-c/${VERSION}/${BLD_NUM}/${ZIP_FILENAME}
fi
unzip ${ZIP_FILENAME}
rm ${ZIP_FILENAME}
popd > /dev/null

# Build
mkdir -p $BUILD_DIR
pushd $BUILD_DIR > /dev/null
cmake -DCMAKE_PREFIX_PATH=$DOWNLOAD_DIR/libcblite-$VERSION -DCMAKE_BUILD_TYPE=Release -DCBL_MACOS_ARCH=x86_64 ..
make -j8 install

# Copy libcblite to
cp $DOWNLOAD_DIR/libcblite-$VERSION/lib/libcblite*.dylib out/bin/

# Copy assets folder
cp -R assets out/bin
popd > /dev/null