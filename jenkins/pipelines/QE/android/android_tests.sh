#!/bin/bash
# Build the Android test server, deploy it, and run the tests

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -eu

BUILD_TOOLS_VERSION='34.0.0'
SDK_MGR="${ANDROID_HOME}/cmdline-tools/latest/bin/sdkmanager"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
export PATH="/opt/homebrew/opt/coreutils/libexec/gnubin:/opt/homebrew/bin:$PATH"
source $SCRIPT_DIR/../../shared/config.sh

function usage() {
    echo "Usage: $0 <cbl_version> <sg_version> [options]"
    echo "  --dataset-version <ver>   CBL dataset version (default: 4.0)"
    echo "  --test-name <expr>        pytest -k expression, or a test path / node id"
    echo "  --setup-only              Build test server + backend only, skip tests"
    exit 1
}

if [ "$#" -lt 2 ]; then usage; fi
CBL_VERSION="$1"
SG_VERSION="$2"
shift 2
[ -n "$CBL_VERSION" ] || usage
[ -n "$SG_VERSION" ] || usage

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

echo "Install Android SDK"
yes | "$SDK_MGR" --channel=1 --licenses
"$SDK_MGR" --channel=1 --install "build-tools;${BUILD_TOOLS_VERSION}"
PATH="${PATH}:$ANDROID_HOME/platform-tools"

echo "Setup backend..."
uv run $SCRIPT_DIR/setup_test.py "$CBL_VERSION" "$SG_VERSION"

if [ "$SETUP_ONLY" = true ]; then
    echo "Setup completed. Exiting due to --setup-only flag."
    exit 0
fi

echo "Start logcat"
pushd $SCRIPT_DIR
python3 logcat.py &
echo $! > logcat.pid
popd

echo "Run tests..."
pushd $QE_TESTS_DIR > /dev/null
adb shell input keyevent KEYCODE_WAKEUP

PYTEST_ARGS=(
    -W ignore::DeprecationWarning
    --config config.json
    --dataset-version "$DATASET_VERSION"
    -m cbl
    --maxfail=7
)

if [ -n "$TEST_NAME" ]; then
    PYTEST_ARGS+=(--no-result-upload)
    if [[ "$TEST_NAME" == *".py"* ]]; then
        PYTEST_ARGS+=("$TEST_NAME")        # path or node id: tests/test_x.py::test_y
    else
        PYTEST_ARGS+=(-k "$TEST_NAME")     # keyword expression
    fi
fi

echo "pytest ${PYTEST_ARGS[*]}"
uv run pytest "${PYTEST_ARGS[@]}"
popd > /dev/null