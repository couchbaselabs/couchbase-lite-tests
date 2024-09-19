#!/bin/bash -e

EDITION=${1}
VERSION=${2}
BLD_NUM=${3}

echo "Build Test Server"
pushd servers/c > /dev/null
./scripts/build_ios.sh device ${EDITION} ${VERSION} ${BLD_NUM}

echo "Run Test Server"
pushd build/out/bin > /dev/null
ios kill com.couchbase.CBLTestServer || true
ios install --path=TestServer.app
ios launch com.couchbase.CBLTestServer

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

rm -f "config.c-ios.json"
cp "${WORKSPACE}/jenkins/pipelines/c/config.c-ios.json" .
pytest -v --no-header -W ignore::DeprecationWarning --config config.c-ios.json
deactivate
popd
