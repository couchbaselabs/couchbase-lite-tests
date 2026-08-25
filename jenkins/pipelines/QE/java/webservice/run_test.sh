#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
source $SCRIPT_DIR/../../../shared/config.sh

function usage() {
  echo "Usage: $0 <version> <sgw_version> [--test-filter EXPR]"
  echo "version: CBL version (e.g. 3.2.1-2)"
  echo "sgw_version: Version of Sync Gateway to download and use"
}

if [ $# -lt 2 ]; then
  usage
  exit 1
fi

cbl_version=$1
sgw_version=$2
shift 2

test_filter=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --test-filter)
      test_filter="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

uv run $SCRIPT_DIR/setup_test.py $cbl_version $sgw_version

pushd $QE_TESTS_DIR
if [ -n "$test_filter" ]; then
  uv run pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json -m cbl -k "$test_filter"
else
  uv run pytest --maxfail=7 -W ignore::DeprecationWarning --config config.json -m cbl
fi
