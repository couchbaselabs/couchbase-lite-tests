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


# Force the Couchbase Lite Java version
pushd servers/jak > /dev/null
echo "$VERSION" > cbl-version.txt

echo "Build Java Desktop Test Server"
cd desktop
./gradlew jar -PbuildNumber="${BUILD_NUMBER}"

echo "Start the Test Server"
if [ -f "server.pid" ]; then kill `cat server.pid`; fi
rm -rf server.log server.url server.pid
nohup java -jar ./app/build/libs/CBLTestServer-Java-Desktop-${VERSION}-${BUILD_NUMBER}.jar server > server.log 2>&1 &
echo $! > server.pid
popd > /dev/null

echo "Start Environment"
jenkins/pipelines/shared/setup_backend.sh "${SG_URL}"

cp -f "jenkins/pipelines/java/desktop/config_java_desktop.json" tests

SERVER_FILE="servers/jak/desktop/server.url"
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

echo "Configure tests"
pushd tests > /dev/null
echo '    "test-servers": ["'"$SERVER_URL"'"]' >> config_java_desktop.json
echo '}' >> config_java_desktop.json
cat config_java_desktop.json

echo "Running tests on desktop test server at $SERVER_URL"
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

echo "Run tests"
pytest -v --no-header -W ignore::DeprecationWarning --config config_java_desktop.json

