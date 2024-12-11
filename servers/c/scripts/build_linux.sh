#!/bin/bash -e

function usage() {
    echo "Usage: $0 <edition: enterprise | community> <cbl-version> <cbl-build-num> <dataset-version>"
    exit 1
}

if [ "$#" -lt 4 ]; then
    usage
fi

EDITION=${1}
VERSION=${2}
BLD_NUM=${3}
DATASET_VERSION=${4}

OS_ARCH=`uname -m`
if [ ${OS_ARCH} = "aarch64" ]
then
  OS_ARCH="arm64"
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
BUILD_DIR="${SCRIPT_DIR}/../build"
LIB_DIR="${SCRIPT_DIR}/../lib"

# Prepare Environment:
"${SCRIPT_DIR}"/prepare_env.sh ${DATASET_VERSION}

# Download CBL:
"${SCRIPT_DIR}"/download_cbl.sh linux ${EDITION} ${VERSION} ${BLD_NUM}

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