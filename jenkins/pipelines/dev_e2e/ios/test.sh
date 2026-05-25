#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

EDITION=${1}
CBL_VERSION=${2}
CBL_BLD_NUM=${3}
SGW_VERSION=${4}
DATASET_VERSION=${5:-"4.0"}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

init_greenboard_results_dir
trap 'uv run python -m cbltest.greenboard_upload \
    --config "$DEV_E2E_TESTS_DIR/config.json" \
    --results-dir "$GREENBOARD_RESULTS_DIR" || true' EXIT

echo "Setup backend..."

uv run $SCRIPT_DIR/setup_test.py $CBL_VERSION-$CBL_BLD_NUM $SGW_VERSION

# Run Tests :
echo "Run tests..."

pushd "${DEV_E2E_TESTS_DIR}" > /dev/null
uv run pytest -v --no-header -W ignore::DeprecationWarning --config config.json --dataset-version $DATASET_VERSION \
    --junitxml="$GREENBOARD_RESULTS_DIR/junit_dev_e2e_ios.xml"
