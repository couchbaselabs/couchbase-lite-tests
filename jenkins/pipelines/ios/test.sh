#!/bin/bash -e

EDITION=${1}
VERSION=${2}
BLD_NUM=${3}

echo "Build Test Server"
pushd servers/ios > /dev/null
./scripts/build.sh device ${EDITION} ${VERSION} ${BLD_NUM}

echo "Run Test Server"
pushd build > /dev/null
ios kill com.couchbase.CBLTestServer-iOS || true
ios install --path=TestServer-iOS.app
ios launch com.couchbase.CBLTestServer-iOS
popd > /dev/null

popd > /dev/null

echo "Start environment"
pushd environment > /dev/null
./start_environment.py
popd > /dev/null

echo "Run tests"
pushd tests
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

rm -f "${WORKSPACE}/jenkins/pipelines/ios/config.ios.json" .
cp "${WORKSPACE}/jenkins/pipelines/ios/config.ios.json" .
pytest -v --no-header -W ignore::DeprecationWarning --config config.ios.json
deactivate
popd
