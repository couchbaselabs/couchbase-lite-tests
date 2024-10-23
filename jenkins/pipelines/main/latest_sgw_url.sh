#!/bin/bash -e

function usage() {
    echo "Usage: $0 <version>"
    exit 1
}

if [ "$#" -ne 1 ]; then
    usage
fi

VERSION=${1}
ARCH=${2}

RESPONSE=$(curl -s "http://proget.build.couchbase.com:8080/api/get_version?product=sync_gateway&version=${VERSION}")
IS_RELEASE=$(echo -n $RESPONSE | jq .IsRelease)
BUILD_NO=$(echo -n $RESPONSE | jq .BuildNumber)
if [ "${BUILD_NO}" == "" ]
then
    echo "No latest successful build found for v${VERSION}"
    exit 3
fi

if [ $IS_RELEASE == true ]; then
    echo -n "https://packages.couchbase.com/releases/couchbase-sync-gateway/$VERSION/couchbase-sync-gateway-enterprise_${VERSION}_<ARCH>.deb"
else
    echo -n "https://latestbuilds.service.couchbase.com/builds/latestbuilds/sync_gateway/$VERSION/$BUILD_NO/couchbase-sync-gateway-enterprise_$VERSION-${BUILD_NO}_<ARCH>.deb"
fi
