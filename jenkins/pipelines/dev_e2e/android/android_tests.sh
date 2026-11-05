#!/bin/bash
# Build the Android test server, deploy it, and run the tests

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -eu # No pipefail because piping yes always "fails" with SIGPIPE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source $SCRIPT_DIR/../../shared/config.sh

function usage() {
  echo "Usage: $0 <cbl_version> <sg_version> [--dataset-version VERSION] [--test-filter EXPR]"
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
      ;;
  esac
done

STATUS=0

PATH="${PATH}:$ANDROID_HOME/platform-tools"

# The workspace is not cleaned between builds, so remove the previous run's logs before anything
# can fail; otherwise the Jenkinsfile would archive them as this run's
rm -rf "$DEV_E2E_TESTS_DIR"/{http_log,testserver.log,session.log*,logcat.txt*} "$DEV_E2E_TESTS_DIR"/*-sgcollectinfo-*.zip

# Capture the device log for the run (install, app start, crashes). CBL's own console lines
# are left out: LogSlurp already collects them. android_teardown.sh stops it; the Jenkinsfile
# archives it.
DEVICE_SERIAL="${ANDROID_SERIAL:-}"
if [ -z "$DEVICE_SERIAL" ]; then
  DEVICE_SERIAL=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["test_servers"][0]["location"])' "$SCRIPT_DIR/topology_single_device.json")
fi

CBL_LOG_TAGS=()
for domain in DATABASE QUERY REPLICATOR NETWORK LISTENER PEER_DISCOVERY MULTIPEER; do
  CBL_LOG_TAGS+=("CouchbaseLite/$domain:S")
done

echo "Start logcat for $DEVICE_SERIAL"
adb -s "$DEVICE_SERIAL" logcat -c || true
adb -s "$DEVICE_SERIAL" logcat -v threadtime "${CBL_LOG_TAGS[@]}" >"$DEV_E2E_TESTS_DIR/logcat.txt" 2>&1 &
echo $! >"$SCRIPT_DIR/logcat.pid"

uv run $SCRIPT_DIR/setup_test.py $CBL_VERSION $SG_VERSION

pushd $DEV_E2E_TESTS_DIR >/dev/null

echo "Run the tests"
if [ -n "$TEST_FILTER" ]; then
  uv run pytest -v --no-header --maxfail=7 -W ignore::DeprecationWarning --config config.json -m min_test_servers --dataset-version "$DATASET_VERSION" --sgcollect-on-test-failure -k "$TEST_FILTER" --no-result-upload
else
  uv run pytest -v --no-header --maxfail=7 -W ignore::DeprecationWarning --config config.json -m min_test_servers --dataset-version "$DATASET_VERSION" --sgcollect-on-test-failure
fi
