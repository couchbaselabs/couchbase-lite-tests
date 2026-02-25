#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
    echo "Usage: $0 <version> <sgw_version> [--setup-only]"
    echo "  --setup-only: Only build test server and setup backend, skip test execution"
    echo "  Build number will be auto-fetched for the specified version"
    exit 1
}

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then usage; fi

CBL_VERSION=${1}
SGW_VERSION=${2}
SETUP_ONLY=false

# Check for --setup-only flag
for arg in "$@"; do
    if [ "$arg" = "--setup-only" ]; then
        SETUP_ONLY=true
        break
    fi
done

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

echo "Setup backend..."

export PATH="/opt/homebrew/bin:$PATH"

uv run $SCRIPT_DIR/setup_test.py $CBL_VERSION $SGW_VERSION
deactivate

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

# Run Tests :
echo "Run tests..."

pushd "${QE_TESTS_DIR}" > /dev/null
uv run pytest -v --no-header -W ignore::DeprecationWarning --config config.json -m cbl
