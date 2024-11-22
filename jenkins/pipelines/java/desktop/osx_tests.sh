#!/bin/bash
# Build the Java Desktop test server, deploy it, and run the tests

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

STATUS=0
CBL_VERSION="${VERSION}-${BUILD_NUMBER}"

pushd servers/jak > /dev/null
SERVER_VERSION=`cat version.txt`
cd desktop

echo "OSX Desktop: Build the Test Server"
rm -rf app/build
./gradlew jar -PcblVersion="${CBL_VERSION}"

echo "OSX Desktop: Start the Test Server"
if [ -f "server.pid" ]; then kill $(cat server.pid); fi
rm -rf server.log server.url server.pid
nohup java -jar "app/build/libs/CBLTestServer-Java-Desktop-${SERVER_VERSION}_${CBL_VERSION}.jar" server > server.log 2>&1 &
echo $! > server.pid
popd > /dev/null

echo "OSX Desktop: Start the environment"
jenkins/pipelines/shared/setup_backend.sh "${SG_URL}"

echo "OSX Desktop: Wait for the Test Server..."
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

echo "OSX Desktop: Configure the tests"
rm -rf tests/config_java_desktop.json
cp -f "jenkins/pipelines/java/desktop/config_java_desktop.json" tests
pushd tests > /dev/null
echo '    "test-servers": ["'"$SERVER_URL"'"]' >> config_java_desktop.json
echo '}' >> config_java_desktop.json
cat config_java_desktop.json

rm -rf venv http_log testserver.log
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

echo "OSX Desktop: Run the tests"
pytest --maxfail=7 -W ignore::DeprecationWarning --config config_java_desktop.json
STATUS=$?

echo "OSX Desktop: Tests complete"
exit $STATUS
