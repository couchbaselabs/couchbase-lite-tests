#!/bin/bash
# Clean up after running Java Web Services tests

function usage() {
    echo "Usage: $0 <version> <build num> [<sg url>]"
    exit 1
}

if [ "$#" -ne 2 ] ; then usage; fi

VERSION="$1"
if [ -z "$VERSION" ]; then usage; fi

BUILD_NUMBER="$2"
if [ -z "$BUILD_NUMBER" ]; then usage; fi

CBL_VERSION="${VERSION}-${BUILD_NUMBER}"
 
echo "OSX Web Service: Shutdown  the Test Server"
pushd servers/jak/webservice > /dev/null
./gradlew appStop -PcblVersion="${CBL_VERSION}" > /dev/null 2>&1 || true
popd > /dev/null

echo "OSX Web Service: Shutdown the environment"
pushd environment > /dev/null
docker compose down
