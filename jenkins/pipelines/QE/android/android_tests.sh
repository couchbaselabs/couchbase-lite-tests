#!/bin/bash
# Build the Android test server, deploy it, and run the tests

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -eu

BUILD_TOOLS_VERSION='34.0.0'
SDK_MGR="${ANDROID_HOME}/cmdline-tools/latest/bin/sdkmanager"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
export PATH="/opt/homebrew/opt/coreutils/libexec/gnubin:/opt/homebrew/bin:$PATH"
source $SCRIPT_DIR/../../shared/config.sh

function usage() {
  echo "Usage: $0 <cbl_version> <sg_version> [--dataset-version VERSION] [--test-filter EXPR] [--setup-only]"
  echo "  --dataset-version: Version of CBL dataset to use (default: 4.0)"
  echo "  --test-filter: An optional pytest -k filter expression"
  echo "  --setup-only: Only build test server and setup backend, skip test execution"
  exit 1
}

if [ "$#" -lt 2 ]; then usage; fi

CBL_VERSION="$1"
if [ -z "$CBL_VERSION" ]; then usage; fi

SG_VERSION="$2"
if [ -z "$SG_VERSION" ]; then usage; fi
shift 2

DATASET_VERSION="4.0"
TEST_FILTER=""
SETUP_ONLY=false

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
echo $! >logcat.pid

echo "Run tests..."
pushd $QE_TESTS_DIR >/dev/null
adb shell input keyevent KEYCODE_WAKEUP
if [ -n "$TEST_FILTER" ]; then
  uv run pytest --maxfail=7 -W ignore::DeprecationWarning \
    --config config.json \
    --dataset-version "$DATASET_VERSION" \
    -m cbl \
    -k "$TEST_FILTER"
else
  uv run pytest --maxfail=7 -W ignore::DeprecationWarning \
    --config config.json \
    --dataset-version "$DATASET_VERSION" \
    -m cbl
fi
