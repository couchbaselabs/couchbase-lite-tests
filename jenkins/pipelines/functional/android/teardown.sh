#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
source $SCRIPT_DIR/../../shared/config.sh

# Stop the logcat capture started by test.sh
if [ -f "$SCRIPT_DIR/logcat.pid" ]; then
  kill "$(cat "$SCRIPT_DIR/logcat.pid")" 2>/dev/null || true
  rm -f "$SCRIPT_DIR/logcat.pid"
fi

pushd $AWS_ENVIRONMENT_DIR >/dev/null
move_artifacts

# Add the logcat to the artifacts move_artifacts saved. Never let this stop the teardown below.
if [ -n "${TS_ARTIFACTS_DIR:-}" ] && [ -f "$FUNCTIONAL_TESTS_DIR/logcat.txt" ]; then
  gzip -f "$FUNCTIONAL_TESTS_DIR/logcat.txt" &&
    mv "$FUNCTIONAL_TESTS_DIR/logcat.txt.gz" "$FUNCTIONAL_TESTS_DIR/$TS_ARTIFACTS_DIR/" ||
    echo "Warning: failed to save logcat.txt"
fi

uv run ./stop_backend.py --topology topology_setup/topology.json
popd >/dev/null
