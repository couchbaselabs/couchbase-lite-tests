#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
  echo "Usage: $0 <cbl_version[-build]> <sgw_version> [--es-version VERSION] [--test-filter EXPR] [--setup-only]"
  echo "  --es-version: Edge Server version (default: the latest release)"
  echo "  --test-filter: An optional pytest -k filter expression (disables result upload)"
  echo "  --setup-only: Only set up the backend and test server, skip test execution"
}

if [ $# -lt 2 ]; then
  usage
  exit 1
fi

CBL_VERSION=${1}
SGW_VERSION=${2}
shift 2

TEST_FILTER=""
ES_VERSION=""
SETUP_ONLY=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --es-version)
      ES_VERSION="$2"
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
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source $SCRIPT_DIR/../../shared/config.sh

if [[ "$(uname)" != "Darwin" ]]; then
  echo "This script only supports macOS"
  exit 1
fi

echo "Setup backend..."
uv run $SCRIPT_DIR/setup_test.py "$CBL_VERSION" "$SGW_VERSION" ${ES_VERSION:+--es-version "$ES_VERSION"}

echo "Install Playwright Chromium..."
uv run playwright install chromium

if [ "$SETUP_ONLY" = true ]; then
  echo "Setup completed. Exiting due to --setup-only flag."
  exit 0
fi

echo "Run tests..."

pushd "${FUNCTIONAL_TESTS_DIR}" >/dev/null
if [ -n "$TEST_FILTER" ]; then
  uv run pytest -v --no-header -W ignore::DeprecationWarning --config config.json -m min_test_servers -k "$TEST_FILTER" --no-result-upload
else
  uv run pytest -v --no-header -W ignore::DeprecationWarning --config config.json -m min_test_servers
fi
