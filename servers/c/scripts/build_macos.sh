#!/bin/bash -e

function usage() {
    echo "Usage: $0 <edition: enterprise | community>  <cbl-version> <cbl-build-num>"
    exit 1
}

if [ "$#" -lt 3 ]; then
    usage
fi

EDITION=${1}
VERSION=${2}
BLD_NUM=${3}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
BUILD_DIR="${SCRIPT_DIR}/../build"
LIB_DIR="${SCRIPT_DIR}/../lib"

# Download CBL:
"${SCRIPT_DIR}"/download_cbl.sh macos ${EDITION} ${VERSION} ${BLD_NUM}

# Build
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"
pushd "${BUILD_DIR}" > /dev/null
cmake -DCMAKE_BUILD_TYPE=Release -DCBL_VERSION=${VERSION} -GNinja ..
ninja install

# Copy libcblite to
cp "${LIB_DIR}"/libcblite/lib/libcblite*.dylib out/bin/

# Copy assets folder
cp -R ${SCRIPT_DIR}/../assets out/bin
popd > /dev/null
