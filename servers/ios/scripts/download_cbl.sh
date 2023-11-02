#!/bin/bash -e

function usage() {
    echo "Usage: $0 <edition: enterprise | community> <version> [build num]"
    exit 1
}

if [ "$#" -lt 3 ]; then
    usage
fi

EDITION=${1}
VERSION=${2}
BLD_NUM=${3}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
DOWNLOAD_DIR="${SCRIPT_DIR}/../download"
FRAMEWORKS_DIR="${SCRIPT_DIR}/../Frameworks"

# Download CBL:
rm -rf "${DOWNLOAD_DIR}" 2> /dev/null
mkdir -p "${DOWNLOAD_DIR}"
pushd "${DOWNLOAD_DIR}" > /dev/null

if [ -z "$BLD_NUM" ]
then
    ZIP_FILENAME=couchbase-lite-swift_xc_${EDITION}_${VERSION}.zip
    curl -O https://packages.couchbase.com/releases/couchbase-lite-ios/${VERSION}/${ZIP_FILENAME}
    echo "https://packages.couchbase.com/releases/couchbase-lite-ios/${VERSION}/${ZIP_FILENAME}"
else
    ZIP_FILENAME=couchbase-lite-swift_xc_${EDITION}_${VERSION}-${BLD_NUM}.zip
    curl -O http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-ios/${VERSION}/${BLD_NUM}/${ZIP_FILENAME}
fi

# Extract the CouchbaseLiteSwift.xcframework:
unzip ${ZIP_FILENAME}
rm -rf "${FRAMEWORKS_DIR}/CouchbaseLiteSwift.xcframework"
cp -r CouchbaseLiteSwift.xcframework "${FRAMEWORKS_DIR}"

popd > /dev/null

rm -rf "${DOWNLOAD_DIR}" 2> /dev/null