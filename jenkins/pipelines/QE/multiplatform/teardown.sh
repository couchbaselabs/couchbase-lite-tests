#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source "$SCRIPT_DIR"/../../shared/config.sh

section_start "$COLOR_GREEN" "TEARDOWN"
export PYTHONPATH=$SCRIPT_DIR/../../../
pushd "$AWS_ENVIRONMENT_DIR" >/dev/null
# The tests run from the tests/ root (QE and dev_e2e in one session), so session.log, http_log and the
# sgcollect/cbcollect zips land in $TESTS_DIR, not $QE_TESTS_DIR.
move_artifacts "$TESTS_DIR"

uv run ./stop_backend.py --topology topology_setup/topology.json
popd >/dev/null
section_end
