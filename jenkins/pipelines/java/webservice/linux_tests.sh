#!/bin/bash
# Build and run the Java WebService test server, and run the tests

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

echo "Download the support libraries"
rm -rf supportlib
mkdir supportlib
curl "${LATESTBUILDS}/${VERSION}/${BUILD_NUMBER}/couchbase-lite-java-linux-supportlibs-${VERSION}-${BUILD_NUMBER}.zip" -o support.zip
unzip -d supportlib support.zip
export LD_LIBRARY_PATH="`pwd`/supportlib:${LD_LIBRARY_PATH}"

echo "Build and start the Java Webservice Test Server"
cd webservice
./gradlew appStop || true
rm -rf server.log app/server.url
nohup ./gradlew jettyStart -PbuildNumber="${BUILD_NUMBER}" < /dev/null > server.log 2>&1 &
popd > /dev/null

echo "Start Server & SG"
pushd environment > /dev/null
./start_environment.py

popd > /dev/null
cp -f "jenkins/pipelines/java/webservice/config_java_webservice.json" tests

echo "Configure tests"
SERVER_URL=`cat servers/jak/webservice/app/server.url`
pushd tests > /dev/null
echo '    "test-servers": ["'"$SERVER_URL"'"]' >> config_java_webservice.json
echo '}' >> config_java_webservice.json
cat config_java_webservice.json

echo "Running tests on webservice test server at $SERVER_IP"
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

echo "Run tests"
pytest -v --no-header -W ignore::DeprecationWarning --config config_java_webservice.json

