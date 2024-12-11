#!/bin/bash -e

EDITION=${1}
CBL_VERSION=${2}
CBL_BLD_NUM=${3}
CBL_DATASET_VERSION=${4}
SGW_URL=${5}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
TEST_SERVER_DIR="${SCRIPT_DIR}/../../../servers/c"
TESTS_DIR="${SCRIPT_DIR}/../../../tests"

echo "Build Test Server"
pushd "${TEST_SERVER_DIR}" > /dev/null
./scripts/build_ios.sh device ${EDITION} ${CBL_VERSION} ${CBL_BLD_NUM} ${CBL_DATASET_VERSION}

echo "Run Test Server"
pushd build/out/bin > /dev/null
ios kill com.couchbase.CBLTestServer || true
ios install --path=TestServer.app
ios launch com.couchbase.CBLTestServer
popd > /dev/null

popd > /dev/null

echo "Start environment"
pushd "${SCRIPT_DIR}/../shared" > /dev/null
./setup_backend.sh ${SGW_URL}
popd > /dev/null

echo "Run tests"
pushd tests
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

rm -f "config.c-ios.json"
cp "${SCRIPT_DIR}/config.c-ios.json" .
pytest -v --no-header -W ignore::DeprecationWarning --config config.c-ios.json
deactivate
popd
