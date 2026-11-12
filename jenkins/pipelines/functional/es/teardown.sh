#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
source $SCRIPT_DIR/../../shared/config.sh

pushd $AWS_ENVIRONMENT_DIR >/dev/null
move_artifacts
# Edge Server diagnostics written by --es-collect when a test fails. Moved after
# move_artifacts, which recreates the artifacts dir empty, so they get archived.
mv "$FUNCTIONAL_TESTS_DIR"/es-collect-*.tar.gz "$FUNCTIONAL_TESTS_DIR/${TS_ARTIFACTS_DIR:-es}/" 2>/dev/null || true

uv run ./stop_backend.py --topology topology_setup/topology.json
popd >/dev/null
