#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../shared/config.sh

export PYTHONPATH=$SCRIPT_DIR/../../../
pushd $AWS_ENVIRONMENT_DIR
move_artifacts

uv sync --no-install-project
uv run --no-project ./stop_backend.py --topology topology_setup/topology.json
popd