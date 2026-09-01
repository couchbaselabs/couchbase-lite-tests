#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
  echo "Usage: $0 <version> <sgw_version> [--dataset-version VERSION] [--test-filter EXPR] [--setup-only]"
  echo "  --dataset-version: Version of CBL dataset to use (default: 4.0)"
  echo "  --test-filter: An optional pytest -k filter expression"
  echo "  --setup-only: Only build test server and setup backend, skip test execution"
  echo "  Build number will be auto-fetched for the specified version"
  exit 1
}

if [ "$#" -lt 2 ]; then usage; fi

CBL_VERSION=${1}
SGW_VERSION=${2}
shift 2

SETUP_ONLY=false
DATASET_VERSION="4.0"
TEST_FILTER=""

# Parse optional arguments
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
    --setup-only)
      SETUP_ONLY=true
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source "$SCRIPT_DIR/../../shared/config.sh"

echo "Setup backend..."

export PATH="/opt/homebrew/bin:$PATH"

uv run "$SCRIPT_DIR/setup_test.py" "$CBL_VERSION" "$SGW_VERSION"

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
  echo "Setup completed. Exiting due to --setup-only flag."
  exit 0
fi

# Run Tests :
echo "Run tests..."

pushd "${QE_TESTS_DIR}" >/dev/null

if [ -n "$TEST_FILTER" ]; then
  uv run pytest -v --no-header -W ignore::DeprecationWarning \
    --config config.json \
    --dataset-version "$DATASET_VERSION" \
    -m cbl \
    -k "$TEST_FILTER" \
    --no-result-upload
else
  uv run pytest -v --no-header -W ignore::DeprecationWarning \
    --config config.json \
    --dataset-version "$DATASET_VERSION" \
    -m cbl
fi
