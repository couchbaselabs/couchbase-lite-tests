#!/bin/bash -e

EDITION=${1}
VERSION=${2}
BLD_NUM=${3}

echo "Build Test Server"
pushd servers/c > /dev/null
./scripts/build_macos.sh ${EDITION} ${VERSION} ${BLD_NUM}

echo "Run Test Server"
pushd build/out/bin > /dev/null
./testserver &> log.txt &
echo $! > testserver.pid
popd > /dev/null

popd > /dev/null

echo "Start environment"
pushd environment > /dev/null
./start_environment.py
popd > /dev/null

echo "Run tests"
pushd tests > /dev/null
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
rm -f "config.c.json"
cp "${WORKSPACE}/jenkins/pipelines/c/config.c.json" .
pytest -v --no-header -W ignore::DeprecationWarning --config config.c.json
deactivate
popd > /dev/null