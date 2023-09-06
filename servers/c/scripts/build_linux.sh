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

OS_ARCH=`uname -m`
if [ ${OS_ARCH} = "aarch64" ]
then
  OS_ARCH="arm64"
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
BUILD_DIR="${SCRIPT_DIR}/../build"
LIB_DIR="${SCRIPT_DIR}/../lib"

# Download CBL:
if [ -z "$BLD_NUM" ]
then
    ${SCRIPT_DIR}/download_cbl.sh linux ${EDITION} ${VERSION}
else
    ${SCRIPT_DIR}/download_cbl.sh linux ${EDITION} ${VERSION} ${BLD_NUM}
fi

# Build
mkdir -p $BUILD_DIR
pushd $BUILD_DIR > /dev/null
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j8 install

# Copy libcblite to
cp ${LIB_DIR}/libcblite/lib/**/libcblite.so* out/bin/

# Copy assets folder
cp -R assets out/bin
popd > /dev/null