#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
source $SCRIPT_DIR/../../shared/config.sh

section_start "$COLOR_GREEN" "TEARDOWN"
export PYTHONPATH=$SCRIPT_DIR/../../../
pushd $AWS_ENVIRONMENT_DIR
# The tests now run from the tests/ root (both QE and dev_e2e in one session),
# so session.log / http_log / junit_result.xml land in $TESTS_DIR, not
# $QE_TESTS_DIR. Pass the source dir explicitly instead of letting
# move_artifacts infer QE vs dev_e2e from the caller path.
move_artifacts "$TESTS_DIR"

uv run ./stop_backend.py --topology topology_setup/topology.json
popd
section_end
