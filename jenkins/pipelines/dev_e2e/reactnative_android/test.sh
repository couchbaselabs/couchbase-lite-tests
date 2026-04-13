#!/bin/bash

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
    echo "Usage: $0 <cbl_version> <sg_version> [dataset_version]"
    exit 1
}

if [ "$#" -lt 2 ] ; then usage; fi

CBL_VERSION="$1"
if [ -z "$CBL_VERSION" ]; then usage; fi

SG_VERSION="$2"
if [ -z "$SG_VERSION" ]; then usage; fi
DATASET_VERSION=${3:-"4.0"}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

# setup_test.py performs the following steps automatically:
#   1. Provisions Couchbase Server and Sync Gateway (Docker containers)
#   2. Downloads the React Native .apk from latestbuilds
#   3. Installs the .apk on the physical Android device via:
#        adb -s <serial> install -r <apk_path>
#   4. Launches the .apk with Android intent extras:
#        --es deviceID ws0  --es wsURL ws://<host_ip>:8765
#      so the app connects to the pytest WebSocket server as soon as it starts.
#
# NOTE: The pytest process below acts as the WebSocket *server* (port 8765).
# The Android app is the WebSocket *client* and is already launched by step 4 above.
# If the app starts before pytest binds port 8765, it will retry until the
# server becomes available (built-in TDK reconnect logic).
uv run $SCRIPT_DIR/setup_test.py $CBL_VERSION $SG_VERSION

pushd $DEV_E2E_TESTS_DIR > /dev/null
rm -rf http_log testserver.log

# Tell the pytest WebSocket router to relaunch the React Native app right after
# it binds port 8765.  This ensures the app's very first connection attempt
# hits a listening port instead of getting ECONNREFUSED and relying on a retry
# window that expires during the pytest startup / collection phase.
#
# setup_test.py already did an initial launch to warm up ART optimisation and
# JS-bundle compilation on the device, so the relaunch done by the router is
# fast (a few seconds).
export CBL_NATIVE_WS_RELAUNCH_SCRIPT="$SCRIPT_DIR/relaunch_app.py"
echo "CBL_NATIVE_WS_RELAUNCH_SCRIPT=$CBL_NATIVE_WS_RELAUNCH_SCRIPT"
echo "Relaunch script exists: $(test -f "$CBL_NATIVE_WS_RELAUNCH_SCRIPT" && echo yes || echo NO - FILE MISSING)"
echo "Python executable used by uv: $(uv run python -c 'import sys; print(sys.executable)')"

echo "Run the React Native Android tests"
uv run pytest \
    --maxfail=7 \
    -v \
    -W ignore::DeprecationWarning \
    --config config.json \
    --dataset-version $DATASET_VERSION \
    --ignore=test_multipeer.py \
    -k "not listener and not multipeer and not custom_conflict" \
    --tb=short \
    --timeout=300
