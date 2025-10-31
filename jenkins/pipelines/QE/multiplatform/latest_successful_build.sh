#!/bin/bash -e

function usage() {
    echo "Usage: $0 <platform: android, c, java, ios, dotnet> <version>"
    echo "Examples:"
    echo "  $0 ios 3.2.3"
    echo "  $0 android 3.1.5"
    echo "  $0 dotnet 3.2.0"
    exit 1
}

if [ "$#" -ne 2 ]; then
    usage
fi

PLATFORM=${1}
VERSION=${2}

# Map platform names to proget API format
if [ "$PLATFORM" == "dotnet" ]; then
    PROGET_PLATFORM="net"
else
    PROGET_PLATFORM="$PLATFORM"
fi

# Validate platform
case $PROGET_PLATFORM in
    ios|android|net|java|c)
        ;;
    *)
        echo "Error: Unsupported platform '$PLATFORM'"
        echo "Supported platforms: ios, android, dotnet, java, c"
        exit 2
        ;;
esac

echo "Fetching latest successful build for $PLATFORM v$VERSION..." >&2

# Use IP address instead of hostname to avoid DNS issues (it works while being connected to vpn.couchbase.com)
BUILD_NO=$(curl -s "http://proget.build.couchbase.com:8080/api/get_version?product=couchbase-lite-${PROGET_PLATFORM}&version=${VERSION}&ee=true" | jq -r .BuildNumber)

if [ "${BUILD_NO}" == "null" ] || [ "${BUILD_NO}" == "" ]; then
    echo "No latest successful build found for ${PLATFORM} v${VERSION}" >&2
    exit 3
fi

echo "Found build ${BUILD_NO} for ${PLATFORM} v${VERSION}" >&2
echo -n ${BUILD_NO} 