#!/bin/bash
# Build and run the Java WebService test server, and run the tests

LATESTBUILDS="https://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-java"

function usage() {
    echo "Usage: $0 <version> <build num> [<sg url>]"
    exit 1
}

if [ "$#" -lt 2 ] | [ "$#" -gt 3 ] ; then usage; fi

VERSION="$1"
if [ -z "$VERSION" ]; then usage; fi

BUILD_NUMBER="$2"
if [ -z "$BUILD_NUMBER" ]; then usage; fi

SG_URL="$3"

# Force the Couchbase Lite Java version
pushd servers/jak > /dev/null
echo "$VERSION" > cbl-version.txt

echo "Linux Web Service: Download the support libraries"
rm -rf supportlib
mkdir supportlib
curl "${LATESTBUILDS}/${VERSION}/${BUILD_NUMBER}/couchbase-lite-java-linux-supportlibs-${VERSION}-${BUILD_NUMBER}.zip" -o support.zip
unzip -d supportlib support.zip
export LD_LIBRARY_PATH="`pwd`/supportlib:${LD_LIBRARY_PATH}"

echo "Linux Web Service: Build and start the Test Server"
cd webservice
./gradlew appStop > /dev/null 2>&1 || true
rm -rf server.log app/server.url
nohup ./gradlew jettyStart -PbuildNumber="${BUILD_NUMBER}" < /dev/null > server.log 2>&1 &
popd > /dev/null

echo "Linux Web Service: Start the environment"
jenkins/pipelines/shared/setup_backend.sh "${SG_URL}"

echo "Linux Web Service: Wait for the Test Server..."
SERVER_FILE="servers/jak/webservice/app/server.url"
SERVER_URL=`cat $SERVER_FILE 2> /dev/null`
n=0
while [[ -z "$SERVER_URL" ]]; do
    if [[ $n -gt 30 ]]; then
        echo "Cannot get server URL: Aborting"
        exit 5
    fi
    ((++n))
    sleep 1
    SERVER_URL=`cat $SERVER_FILE 2> /dev/null`
done

echo "Linux Web Service: Configure the tests"
rm -rf tests/config_java_webservice.json
cp -f "jenkins/pipelines/java/webservice/config_java_webservice.json" tests
pushd tests > /dev/null
echo '    "test-servers": ["'"$SERVER_URL"'"]' >> config_java_webservice.json
echo '}' >> config_java_webservice.json
cat config_java_webservice.json

rm -rf venv
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

echo "Linux Web Service: Run the tests"
pytest --maxfail=7 -W ignore::DeprecationWarning --config config_java_webservice.json

echo "Linux Web Service: Tests complete"

