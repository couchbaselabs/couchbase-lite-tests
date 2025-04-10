#!/bin/bash -e

EDITION=${1}
CBL_VERSION=${2}
CBL_BLD_NUM=${3}
CBL_DATASET_VERSION=${4}
SGW_VERSION=${5}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SHARED_DIR="${SCRIPT_DIR}/../shared"
TEST_SERVER_DIR="${SCRIPT_DIR}/../../../servers/ios"
TESTS_DIR="${SCRIPT_DIR}/../../../tests/dev_e2e"

echo "Setup backend..."

python3.10 -m venv venv
source venv/bin/activate
pip install -r $SCRIPT_DIR/../../../environment/aws/requirements.txt
if [ -n "$private_key_path" ]; then
    python3.10 $SCRIPT_DIR/setup_test.py $CBL_VERSION $DATASET_VERSION $SG_VERSION --private_key $private_key_path
else
    python3.10 $SCRIPT_DIR/setup_test.py $CBL_VERSION $DATASET_VERSION $SG_VERSION
fi
deactivate

# Run Tests :
echo "Run tests..."

pushd "${TESTS_DIR}" > /dev/null
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
sed "s/{{test-server-ip}}/${TEST_SERVER_IP}/g" $SCRIPT_DIR/config.json | sed "s/{{test-client-ip}}/${TEST_CLIENT_IP}/g" > config.json
pytest -v --no-header -W ignore::DeprecationWarning --config config.json
deactivate
popd > /dev/null
