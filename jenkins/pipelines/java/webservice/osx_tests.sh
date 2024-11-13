#!/bin/bash
# Build and run the Java WebService test server, and run the tests

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

# Force the Couchbase Lite Java version
pushd servers/jak > /dev/null
echo "$VERSION" > cbl-version.txt

echo "OSX Web Service: Build and start the Java Webservice Test Server"
cd webservice
./gradlew appStop > /dev/null 2>&1 || true
rm -rf server.log app/server.url
nohup ./gradlew jettyStart -PbuildNumber="${BUILD_NUMBER}" < /dev/null > server.log 2>&1 &
popd > /dev/null

echo "OSX Web Service: Start the environment"
jenkins/pipelines/shared/setup_backend.sh "${SG_URL}"

echo "OSX Web Service: Wait for the Test Server..."
SERVER_FILE="servers/jak/webservice/app/server.url"
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

echo "OSX Web Service: Configure the tests"
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

echo "OSX Web Service: Run the tests"
pytest --maxfail=7 -W ignore::DeprecationWarning --config config_java_webservice.json
STATUS=$?

echo "OSX Web Service: Tests complete!"
exit $STATUS
