#!/bin/bash
# Build the Java Desktop test server, deploy it, and run the tests

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

echo "Linux Desktop: Build the Test Server"
cd desktop
./gradlew jar -PbuildNumber="${BUILD_NUMBER}"

echo "Linux Desktop: Download the support libraries"
rm -rf supportlib
mkdir supportlib
curl "${LATESTBUILDS}/${VERSION}/${BUILD_NUMBER}/couchbase-lite-java-linux-supportlibs-${VERSION}-${BUILD_NUMBER}.zip" -o support.zip
unzip -d supportlib support.zip
export LD_LIBRARY_PATH="$(pwd)/supportlib:${LD_LIBRARY_PATH}"

echo "Linux Desktop: Start the Test Server"
if [ -f "server.pid" ]; then kill $(cat server.pid); fi
rm -rf server.log server.url server.pid
nohup java -jar "app/build/libs/CBLTestServer-Java-Desktop-${VERSION}-${BUILD_NUMBER}.jar" server > server.log 2>&1 &
echo $! > server.pid
popd > /dev/null

echo "Linux Desktop: Start the environment"
jenkins/pipelines/shared/setup_backend.sh "${SG_URL}"

echo "Linux Desktop: Wait for the Test Server..."
SERVER_FILE="servers/jak/desktop/server.url"
SERVER_URL=$(cat $SERVER_FILE 2> /dev/null)
n=0
while [[ -z "$SERVER_URL" ]]; do
    if [[ $n -gt 30 ]]; then
        echo "Cannot get server URL: Aborting"
        exit 5
    fi
    ((++n))
    sleep 1
    SERVER_URL=$(cat $SERVER_FILE 2> /dev/null)
done

echo "Linux Desktop: Configure the tests"
rm -rf tests/config_java_desktop.json
cp -f "jenkins/pipelines/java/desktop/config_java_desktop.json" tests
pushd tests > /dev/null
echo '    "test-servers": ["'"$SERVER_URL"'"]' >> config_java_desktop.json
echo '}' >> config_java_desktop.json
cat config_java_desktop.json

rm -rf venv
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

echo "Linux Desktop: Run the tests"
pytest --maxfail=7 -W ignore::DeprecationWarning --config config_java_desktop.json

echo "Linux Desktop: Tests complete!"
