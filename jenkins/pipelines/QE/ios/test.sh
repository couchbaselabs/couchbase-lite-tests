#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
    echo "Usage: $0 <version> <sgw_version> [options]"
    echo "  --dataset-version <ver>  Version of CBL dataset to use (default: 4.0)"
    echo "  --test-name <expr>       pytest -k expression, or a test path"
    echo "  --setup-only             Only build test server and setup backend, skip tests"
    echo "  Build number will be auto-fetched for the specified version"
    exit 1
}

if [ "$#" -lt 2 ]; then usage; fi

CBL_VERSION="$1"
SGW_VERSION="$2"
shift 2
[ -n "$CBL_VERSION" ] || usage
[ -n "$SGW_VERSION" ] || usage

SETUP_ONLY=false
DATASET_VERSION="4.0"
TEST_NAME=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dataset-version) DATASET_VERSION="${2:-}"; shift 2 ;;
        --test-name)       TEST_NAME="${2:-}";       shift 2 ;;
        --setup-only)      SETUP_ONLY=true;          shift   ;;
        "")                shift ;;   # tolerate empty args from Jenkins interpolation
        *) echo "Unknown option: $1"; usage ;;
    esac
done
[ -n "$DATASET_VERSION" ] || DATASET_VERSION="4.0"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
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

pushd "${QE_TESTS_DIR}" > /dev/null

PYTEST_ARGS=(
    -v --no-header
    -W ignore::DeprecationWarning
    --config config.json
    --dataset-version "$DATASET_VERSION"
    -m cbl
    --maxfail=7
)

if [ -n "$TEST_NAME" ]; then
    if [[ "$TEST_NAME" == *".py"* ]]; then
        PYTEST_ARGS+=("$TEST_NAME")        # path
    else
        PYTEST_ARGS+=(-k "$TEST_NAME")     # keyword expression
    fi
fi

echo "pytest ${PYTEST_ARGS[*]}"
set +e
uv run pytest "${PYTEST_ARGS[@]}"
PYTEST_RC=$?
set -e
popd > /dev/null

if [ "$PYTEST_RC" -eq 5 ]; then
    echo "ERROR: no tests collected. TEST_NAME='${TEST_NAME}' matched nothing under -m cbl."
fi
exit $PYTEST_RC