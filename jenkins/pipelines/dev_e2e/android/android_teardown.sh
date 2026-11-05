#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
source $SCRIPT_DIR/../../shared/config.sh

# Stop the logcat capture started by android_tests.sh
if [ -f "$SCRIPT_DIR/logcat.pid" ]; then
  kill "$(cat "$SCRIPT_DIR/logcat.pid")" 2>/dev/null || true
  rm -f "$SCRIPT_DIR/logcat.pid"
fi

# Compress the logs for archiving (session.log can reach ~200 MB). Never let this stop the
# teardown below: an uncompressed log is still archived.
for log in logcat.txt session.log; do
  if [ -f "$DEV_E2E_TESTS_DIR/$log" ]; then
    gzip -f "$DEV_E2E_TESTS_DIR/$log" ||
      echo "Warning: failed to gzip $log; leaving it uncompressed"
  fi
done

pushd $AWS_ENVIRONMENT_DIR
uv run ./stop_backend.py --topology topology_setup/topology.json
