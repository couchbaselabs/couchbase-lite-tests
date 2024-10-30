#!/bin/bash -e

EDITION=${1}
VERSION=${2}
BLD_NUM=${3}
SGW_URL=${4}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
TEST_SERVER_DIR="${SCRIPT_DIR}/../../../servers/c"
TESTS_DIR="${SCRIPT_DIR}/../../../tests"

echo "Build Test Server"
pushd "${TEST_SERVER_DIR}" > /dev/null
./scripts/build_linux.sh ${EDITION} ${VERSION} ${BLD_NUM}

echo "Run Test Server"
pushd build/out/bin > /dev/null
./testserver &> log.txt &
echo $! > testserver.pid
popd > /dev/null

popd > /dev/null

echo "Start environment"
pushd "${SCRIPT_DIR}/../shared" > /dev/null
./setup_backend.sh ${SGW_URL}
popd > /dev/null

echo "Run tests"
pushd "${TESTS_DIR}" > /dev/null
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

rm -f "config.c.json"
cp "${SCRIPT_DIR}/config.c.json" .
pytest -v --no-header -W ignore::DeprecationWarning --config config.c.json
deactivate
popd > /dev/null