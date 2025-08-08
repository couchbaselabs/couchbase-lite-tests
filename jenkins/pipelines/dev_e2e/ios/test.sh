#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

EDITION=${1}
CBL_VERSION=${2}
CBL_BLD_NUM=${3}
SGW_VERSION=${4}
private_key_path=${5}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh
export UV_PYTHON="3.10"

echo "Setup backend..."

if [ -n "$private_key_path" ]; then
    uv run --project $AWS_ENVIRONMENT_DIR/pyproject.toml $SCRIPT_DIR/setup_test.py $CBL_VERSION-$CBL_BLD_NUM $SGW_VERSION --private_key $private_key_path
else
    uv run --project $AWS_ENVIRONMENT_DIR/pyproject.toml $SCRIPT_DIR/setup_test.py $CBL_VERSION-$CBL_BLD_NUM $SGW_VERSION
fi

# Run Tests :
echo "Run tests..."

pushd "${DEV_E2E_TESTS_DIR}" > /dev/null
uv run pytest -v --no-header -W ignore::DeprecationWarning --config config.json
