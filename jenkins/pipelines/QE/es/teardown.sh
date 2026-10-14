#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
source $SCRIPT_DIR/../../shared/config.sh

pushd $AWS_ENVIRONMENT_DIR
# Passing the generated topology also stops its test servers, such as the JS test server on localhost.
if [ -f topology_setup/topology.json ]; then
  uv run ./stop_backend.py --topology topology_setup/topology.json
else
  uv run ./stop_backend.py
fi
