#!/bin/bash -e

function usage() {
  echo "Usage: $0 <edition> <cbl-version> <cbl-build-num>"
  exit 1
}

if [ "$#" -lt 3 ]; then
  usage
fi

EDITION=${1}
VERSION=${2}
BLD_NUM=${3}

OS_ARCH=$(uname -m)
if [ ${OS_ARCH} = "aarch64" ]; then
  OS_ARCH="arm64"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
BUILD_DIR="${SCRIPT_DIR}/../build"
LIB_DIR="${SCRIPT_DIR}/../lib"
ASSETS_DIR="${SCRIPT_DIR}/../assets"

# Download CBL:
"${SCRIPT_DIR}"/download_cbl.sh linux "${EDITION}" ${VERSION} ${BLD_NUM}

# Build
rm -rf "${BUILD_DIR}"
mkdir -p $BUILD_DIR
pushd $BUILD_DIR >/dev/null
cmake -DCBL_VERSION=${VERSION} -DCMAKE_BUILD_TYPE=Release ..
make -j8 install

# Copy libcblite to
cp ${LIB_DIR}/libcblite/lib/**/libcblite.so* out/bin/

# Copy assets folder. The server looks for it next to its own directory, as <executable>/../assets.
mkdir -p out/assets
cp -R "${ASSETS_DIR}/." out/assets/
popd >/dev/null
