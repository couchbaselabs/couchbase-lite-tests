#!/bin/bash -e

function usage() {
    echo "Usage: $0 <platform: android, c, java, ios, net> <version>"
    exit 1
}

if [ "$#" -ne 2 ]; then
    usage
fi

PLATFORM=${1}
VERSION=${2}

BUILD_NO=$(curl -s "http://proget.build.couchbase.com:8080/api/get_version?product=couchbase-lite-${PLATFORM}&version=${VERSION}&ee=true" | jq .BuildNumber)
if [ "${BUILD_NO}" == "" ]
then
    echo "No latest successful build found for ${PLATFORM} v${VERSION}"
    exit 3
fi

echo -n ${BUILD_NO}
