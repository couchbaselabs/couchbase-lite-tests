#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../shared/config.sh

export PYTHONPATH=$SCRIPT_DIR/../../../
pushd $AWS_ENVIRONMENT_DIR

# Best-effort sg_collect; failures must never stop teardown (avoid leaked EC2s).
# Zips land in the QE tests dir and move_artifacts places them in
# TS_ARTIFACTS_DIR, Jenkins archives them under its normal retention.
uv run ./sg_collect.py --topology topology_setup/topology.json --output-dir "$QE_TESTS_DIR" || \
  echo "WARNING: sg_collect.py failed; continuing with teardown"
move_artifacts

uv run ./stop_backend.py --topology topology_setup/topology.json
popd
