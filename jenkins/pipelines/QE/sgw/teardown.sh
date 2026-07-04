#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../shared/config.sh

export PYTHONPATH=$SCRIPT_DIR/../../../
pushd $AWS_ENVIRONMENT_DIR

# Best-effort sg_collect upload; failures must never stop teardown (avoid leaked EC2s).
# BUILD_NUMBER (set by Jenkins) is truncated to the last 7 digits to satisfy SGW ticket validation.
ticket_opt=()
if [[ -n "${BUILD_NUMBER-}" ]]; then
  ticket_opt=(--ticket "${BUILD_NUMBER: -7}")
fi
uv run ./sg_collect.py --topology topology_setup/topology.json "${ticket_opt[@]}" || \
  echo "WARNING: sg_collect.py failed; continuing with teardown"
move_artifacts

uv run ./stop_backend.py --topology topology_setup/topology.json
popd
