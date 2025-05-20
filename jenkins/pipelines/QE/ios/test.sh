#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

EDITION=${1}
CBL_VERSION=${2}
CBL_BLD_NUM=${3}
CBL_DATASET_VERSION=${4}
SGW_VERSION=${5}
private_key_path=${6}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

echo "Setup backend..."

create_venv venv
source venv/bin/activate
pip install -r $AWS_ENVIRONMENT_DIR/requirements.txt
if [ -n "$private_key_path" ]; then
   python3 $SCRIPT_DIR/setup_test.py $CBL_VERSION-$CBL_BLD_NUM $CBL_DATASET_VERSION $SGW_VERSION --private_key $private_key_path
else
   python3 $SCRIPT_DIR/setup_test.py $CBL_VERSION-$CBL_BLD_NUM $CBL_DATASET_VERSION $SGW_VERSION
fi
deactivate

# Run Tests :
echo "Run tests..."

pushd "${QE_TESTS_DIR}" > /dev/null
create_venv venv
. venv/bin/activate
pip install -r requirements.txt
pytest -v --no-header -W ignore::DeprecationWarning --config config.json test_delta_sync.py
deactivate
popd > /dev/null
