#!/bin/bash
# Build and run the java Desktop test server

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
ROOT_DIR="${SCRIPT_DIR}"/../../../..

function usage() {
    echo "Usage: $0 <cbl version> <dataset version>"
    exit 1
}

if [ "$#" -ne 2 ] ; then usage; fi

CBL_VERSION="$1"
if [ -z "$CBL_VERSION" ]; then usage; fi

DATASET_VERSION="$2"
if [ -z "$DATASET_VERSION" ]; then usage; fi

cd "${ROOT_DIR}"/servers/jak
SERVER_VERSION=`cat version.txt`
cd desktop

rm -rf app/build
./gradlew jar -PcblVersion="${CBL_VERSION}" -PdatasetVersion="${DATASET_VERSION}" | exit 1

echo "==== Running Test Server $SERVER_VERSION with CBL $CBL_VERSION and dataset ${DATASET_VERSION}"
java -jar "app/build/libs/CBLTestServer-Java-Desktop-${SERVER_VERSION}_${CBL_VERSION}.jar" | exit 1

