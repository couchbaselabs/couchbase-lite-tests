#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
  echo "Usage: $0 <edition> <cbl_version> <cbl_build> <sgw_version> [--dataset-version VERSION] [--test-filter EXPR]"
}

if [ $# -lt 4 ]; then
  usage
  exit 1
fi

EDITION=${1}
CBL_VERSION=${2}
CBL_BLD_NUM=${3}
SGW_VERSION=${4}
shift 4

DATASET_VERSION="4.0"
TEST_FILTER=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dataset-version)
      DATASET_VERSION="$2"
      shift 2
      ;;
    --test-filter)
      TEST_FILTER="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source $SCRIPT_DIR/../../shared/config.sh

echo "Setup backend..."

uv run $SCRIPT_DIR/setup_test.py $CBL_VERSION-$CBL_BLD_NUM $SGW_VERSION

# Run Tests :
echo "Run tests..."

pushd "${DEV_E2E_TESTS_DIR}" >/dev/null
if [ -n "$TEST_FILTER" ]; then
  uv run pytest -v --no-header -W ignore::DeprecationWarning --config config.json --dataset-version "$DATASET_VERSION" -k "$TEST_FILTER" --no-result-upload
else
  uv run pytest -v --no-header -W ignore::DeprecationWarning --config config.json --dataset-version "$DATASET_VERSION"
fi
