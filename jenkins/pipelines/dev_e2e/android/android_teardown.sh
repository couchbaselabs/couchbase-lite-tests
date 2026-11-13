#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
source $SCRIPT_DIR/../../shared/config.sh

# Stop the logcat capture started by android_tests.sh
if [ -f "$SCRIPT_DIR/logcat.pid" ]; then
  kill "$(cat "$SCRIPT_DIR/logcat.pid")" 2>/dev/null || true
  rm -f "$SCRIPT_DIR/logcat.pid"
fi

move_artifacts

# Add the logcat to the artifacts move_artifacts saved. Never let this stop the teardown below.
if [ -n "${TS_ARTIFACTS_DIR:-}" ] && [ -f "$DEV_E2E_TESTS_DIR/logcat.txt" ]; then
  gzip -f "$DEV_E2E_TESTS_DIR/logcat.txt" &&
    mv "$DEV_E2E_TESTS_DIR/logcat.txt.gz" "$DEV_E2E_TESTS_DIR/$TS_ARTIFACTS_DIR/" ||
    echo "Warning: failed to save logcat.txt"
fi

pushd $AWS_ENVIRONMENT_DIR
uv run ./stop_backend.py --topology topology_setup/topology.json
