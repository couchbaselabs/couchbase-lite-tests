#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
source $SCRIPT_DIR/../../shared/config.sh

pkill -f -- "--user-data-dir=${HOME}/.tdk-chrome" || true
move_artifacts
cp "${HOME}/.tdk-chrome/chrome_debug.log" "${DEV_E2E_TESTS_DIR}/${TS_ARTIFACTS_DIR:-}/" || true

pushd $AWS_ENVIRONMENT_DIR
uv run ./stop_backend.py --topology topology_setup/topology.json
