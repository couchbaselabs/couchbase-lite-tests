#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
source $SCRIPT_DIR/../../shared/config.sh

pushd $AWS_ENVIRONMENT_DIR
for d in "$QE_TESTS_DIR/edge_server" "$DEV_E2E_TESTS_DIR/edge_server"; do
  move_artifacts "$d"
done

uv run ./stop_backend.py --topology topology_setup/topology.json
