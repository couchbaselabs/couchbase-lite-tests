#!/bin/bash -e

function usage() {
    echo "Usage: $0 <cbl-version> <cbl-build-num>"
    exit 1
}

if [ "$#" -lt 3 ]; then
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
"${SCRIPT_DIR}"/download_cbl.sh linux "enterprise" ${VERSION} ${BLD_NUM}

# Build
rm -rf "${BUILD_DIR}"
mkdir -p $BUILD_DIR
pushd $BUILD_DIR > /dev/null
cmake -DCBL_VERSION=${VERSION} -DCMAKE_BUILD_TYPE=Release ..
make -j8 install

# Copy libcblite to
cp ${LIB_DIR}/libcblite/lib/**/libcblite.so* out/bin/

# Copy assets folder
cp -R assets out/bin
popd > /dev/null