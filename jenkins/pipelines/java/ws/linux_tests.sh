#!/bin/bash
# Build the Java WebService  test server, deploy it, and run the tests

function usage() {
    echo "Usage: $0 <edition> <version> <build num>"
    exit 1
}

if [ "$#" -ne 3 ]; then usage; fi

EDITION="$1"
if [ -z "$EDITION" ]; then usage; fi

VERSION="$2"
if [ -z "$VERSION" ]; then usage; fi

BUILD_NUMBER="$3"
if [ -z "$BUILD_NUMBER" ]; then usage; fi

# Force the Couchbase Lite Java version
pushd servers/jak > /dev/null
echo "$VERSION" > cbl-version.txt

echo "Build and start the Java Webservice Test Server"
cd webservice
if [ -f "server.pid" ]; then kill `cat server.pid`; fi
rm -rf server.log server.url server.pid
# !!! will this run without the terminal, and will its pid be enough to stop it?
nohup ./gradlew jettyStart -PbuildNumber="${BUILD_NUMBER}" > server.log 2>&1 &
echo $! > server.pid
popd > /dev/null

echo "Start Server & SG"
pushd environment > /dev/null
./start_environment.py

popd > /dev/null
cp -f "jenkins/pipelines/java/desktop/config.ws_java.json" tests

echo "Configure tests"
SERVER_URL=`cat servers/jak/webservice/server.url`
pushd tests > /dev/null
echo '    "test-servers": ["'"$SERVER_URL"'"]' >> config.ws_java.json
echo '}' >> config.ws_java.json
cat config.ws_java.json

echo "Running tests on desktop test server at $SERVER_IP"
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

echo "Run tests"
pytest -v --no-header -W ignore::DeprecationWarning --config config.desktop_java.json

