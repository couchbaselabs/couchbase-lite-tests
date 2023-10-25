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

BUILD_NO=""
if [ "${PLATFORM}" == "android" ]
then
    BUILD_NO=`curl -s https://raw.githubusercontent.com/couchbase/build-manifests/master/couchbase-lite-android/${VERSION}/${VERSION}.xml |  xmllint --xpath "//manifest/project/annotation[3]/@value" - | cut -f 2 -d "=" | cut -f 2 -d "\""`
elif [ "${PLATFORM}" == "java" ]
then
    BUILD_NO=`curl -s http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-java/${VERSION}/lastSuccessful.xml | xmllint --xpath "//manifest/project/annotation[3]/@value" - | cut -f 2 -d "=" | cut -f 2 -d "\""`
elif [ "${PLATFORM}" == "ios" ]
then
    BUILD_NO=`curl -s https://raw.githubusercontent.com/couchbase/build-manifests/master/couchbase-lite-ios/${VERSION}/${VERSION}.xml |  xmllint --xpath "//manifest/project/annotation[3]/@value" - | cut -f 2 -d "=" | cut -f 2 -d "\""`
elif [ "${PLATFORM}" == "net" ]
then
    BUILD_NO=`curl -s "https://proget.sc.couchbase.com/nuget/Internal/FindPackagesById()?id='Couchbase.Lite.Enterprise'" | sed -e 's/xmlns="[^"]*"//g' | sed -e 's/[m|d]://g' | xmllint --xpath '//feed/entry[*]/properties/Version/text()' - | sort -r | grep "^${VERSION}-" -m 1 | awk -F'-' '{print $2}'`
elif [ "${PLATFORM}" == "c" ]
then
    BUILD_NO=`curl -s http://dbapi.build.couchbase.com:8000/v1/products/couchbase-lite-c/releases/${VERSION}/versions/${VERSION}/builds?filter=last_complete | cut -f 2 -d ":" | cut -f 2 -d "\""`
else
    echo "Invalid platform : ${PLATFORM}"
    exit 2
fi

if [ "${BUILD_NO}" == "" ]
then
    echo "No latest successful build found for ${PLATFORM} v${VERSION}"
    exit 3
fi

echo -n ${BUILD_NO}
