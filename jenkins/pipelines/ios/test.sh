#!/bin/bash -e

EDITION=${1}
VERSION=${2}
BLD_NUM=${3}
SGW_URL=${4}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
TEST_SERVER_DIR="${SCRIPT_DIR}/../../../servers/ios"
TESTS_DIR="${SCRIPT_DIR}/../../../tests"

echo "Build Test Server"
pushd "${TEST_SERVER_DIR}" > /dev/null
./scripts/build.sh device ${EDITION} ${VERSION} ${BLD_NUM}

echo "Run Test Server"
pushd build > /dev/null
ios kill com.couchbase.CBLTestServer-iOS || true
ios install --path=TestServer-iOS.app
ios launch com.couchbase.CBLTestServer-iOS
popd > /dev/null

popd > /dev/null

echo "Start environment"
pushd "${SCRIPT_DIR}/../shared" > /dev/null
./setup_backend.sh ${SGW_URL}
popd > /dev/null

echo "Run tests"
pushd "${TESTS_DIR}"
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

rm -f "config.ios.json" || true
cp "${SCRIPT_DIR}/config.ios.json" .
pytest -v --no-header -W ignore::DeprecationWarning --config config.ios.json
deactivate
popd
