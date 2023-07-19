#!/bin/sh

VERSION=$1
BUILD_NUM=$2
ARTIFACTS_DIR=$3

function usage() {
   echo "Usage: $0 <version> <build#> <artifacts dir>"
   exit 1
}

if [ -z "${VERSION}" ]; then usage; fi
if [ -z "${BUILD_NUM}" ]; then usage; fi
if [ -z "${ARTIFACTS_DIR}" ] || [ ! -d "${ARTIFACTS_DIR}" ]; then
    echo "Directory not found: $ARTIFACTS_DIR"
    usage
fi

export PATH=$PATH:$JAVA_HOME

MAVEN_UPLOAD_VERSION=${VERSION}-${BUILD_NUM}
TESTSERVER="CBLTestServer-Java-Desktop-${MAVEN_UPLOAD_VERSION}"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

pushd "${SCRIPT_DIR}/.."
echo "Building version ${MAVEN_UPLOAD_VERSION}"
./gradlew -Dversion=${MAVEN_UPLOAD_VERSION} clean assemble

find "app/build/libs"
rm -rf "${SCRIPT_DIR}/${TESTSERVER}.jar"
cp -f "app/build/libs/${TESTSERVER}.jar" "${SCRIPT_DIR}"

cd $SCRIPT_DIR
zip "${TESTSERVER}.zip" "${TESTSERVER}.jar" daemon_manager.sh win_service_manager.bat
mv -f "${TESTSERVER}.zip" "${ARTIFACTS_DIR}"
rm -rf "${SCRIPT_DIR}/${TESTSERVER}.jar"

popd > /dev/null

