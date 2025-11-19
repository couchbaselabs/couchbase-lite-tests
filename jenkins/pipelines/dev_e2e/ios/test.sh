#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

EDITION=${1}
CBL_VERSION=${2}
CBL_BLD_NUM=${3}
SGW_VERSION=${4}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

echo "Setup backend..."

stop_venv
create_venv venv
source venv/bin/activate
trap stop_venv EXIT
uv pip install -r $AWS_ENVIRONMENT_DIR/requirements.txt
python3 $SCRIPT_DIR/setup_test.py $CBL_VERSION-$CBL_BLD_NUM $SGW_VERSION

# Run Tests :
echo "Run tests..."

pushd "${DEV_E2E_TESTS_DIR}" > /dev/null
uv pip install -r requirements.txt
pytest -v --no-header -W ignore::DeprecationWarning --config config.json
