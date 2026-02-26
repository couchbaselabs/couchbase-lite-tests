#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

echo "Tearing down multiplatform test environment..."

# Teardown AWS backend resources (SGW and CBS)
echo "Stopping AWS backend resources..."
pushd $AWS_ENVIRONMENT_DIR
uv run ./stop_backend.py --topology topology_setup/topology.json

echo "Multiplatform teardown complete."
