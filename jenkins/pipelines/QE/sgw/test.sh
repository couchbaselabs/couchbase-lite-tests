#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
    echo "Usage: $0 <edition> <version> <sgw_version> <private_key_path> [--setup-only]"
    echo "  --setup-only: Only build test server and setup backend, skip test execution"
    echo "  Build number will be auto-fetched for the specified version"
    exit 1
}

if [ "$#" -lt 4 ] || [ "$#" -gt 5 ]; then usage; fi

EDITION=${1}
CBL_VERSION=${2}
SGW_VERSION=${3}
private_key_path=${4}
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

create_venv venv
source venv/bin/activate
pip install -r $AWS_ENVIRONMENT_DIR/requirements.txt
if [ -n "$private_key_path" ]; then
   python3 $SCRIPT_DIR/setup_test.py $CBL_VERSION $SGW_VERSION --private_key $private_key_path
else
   python3 $SCRIPT_DIR/setup_test.py $CBL_VERSION $SGW_VERSION
fi
deactivate

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

# Run Tests :
echo "Run tests..."

pushd "${QE_TESTS_DIR}" > /dev/null
create_venv venv
. venv/bin/activate
pip install -r requirements.txt
pytest -v --no-header -W ignore::DeprecationWarning --config config.json -m sgw
deactivate
popd > /dev/null
