#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
source $SCRIPT_DIR/../../shared/config.sh

# Stop the logcat capture test.sh started and keep its per-test logs
if [ -f "$SCRIPT_DIR/logcat.pid" ]; then
  kill "$(cat "$SCRIPT_DIR/logcat.pid")" 2>/dev/null || true
  rm -f "$SCRIPT_DIR/logcat.pid"
fi

pushd $AWS_ENVIRONMENT_DIR >/dev/null
move_artifacts
if [ -n "${TS_ARTIFACTS_DIR:-}" ]; then
  mv "$SCRIPT_DIR"/logs_* "$FUNCTIONAL_TESTS_DIR/$TS_ARTIFACTS_DIR/" 2>/dev/null || true
fi

uv run ./stop_backend.py --topology topology_setup/topology.json
popd >/dev/null
