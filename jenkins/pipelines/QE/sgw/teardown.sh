#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../shared/config.sh

export PYTHONPATH=$SCRIPT_DIR/../../../
pushd $AWS_ENVIRONMENT_DIR

# Best-effort sg_collect upload; failures must never stop teardown (avoid leaked EC2s).
# BUILD_NUMBER (set by Jenkins) groups the run's uploads under one
# "<customer>/<ticket>/" folder in the support portal.
uv run ./sg_collect.py --topology topology_setup/topology.json \
    ${BUILD_NUMBER:+--ticket "${BUILD_NUMBER: -7}"} || \
    echo "WARNING: sg_collect.py failed; continuing with teardown"
move_artifacts

uv run ./stop_backend.py --topology topology_setup/topology.json
popd
