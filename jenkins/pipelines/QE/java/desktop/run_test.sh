#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR/../../../shared/config.sh"

function usage() {
    echo "Usage: $0 <version> <sgw_version> [options]"
    echo "  version:      CBL version (e.g. 3.2.1-2)"
    echo "  sgw_version:  Version of Sync Gateway to download and use"
    echo "  --dataset-version <ver>  Dataset version (default: 4.0)"
    echo "  --test-name <expr>       pytest -k expression, or a test path"
    echo "  --setup-only             Build test server + backend only, skip tests"
    exit 1
}

if [ "$#" -lt 2 ]; then usage; fi
cbl_version="$1"
sgw_version="$2"
shift 2
[ -n "$cbl_version" ] || usage
[ -n "$sgw_version" ] || usage

DATASET_VERSION="4.0"
TEST_NAME=""
SETUP_ONLY=false

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

uv run "$SCRIPT_DIR/setup_test.py" "$cbl_version" "$sgw_version"

if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

pushd "$QE_TESTS_DIR" > /dev/null

PYTEST_ARGS=(
    -W ignore::DeprecationWarning
    --config config.json
    --dataset-version "$DATASET_VERSION"
    -m cbl
    --maxfail=7
)

if [ -n "$TEST_NAME" ]; then
    if [[ "$TEST_NAME" == *".py"* ]]; then
        PYTEST_ARGS+=("$TEST_NAME")
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