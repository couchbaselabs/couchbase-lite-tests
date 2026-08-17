#!/bin/bash

# Best-effort SGW diagnostics collection, invoked from the Jenkinsfile
# post{always} path BEFORE teardown. Running here (not inside pytest) means it
# still executes when a run times out or is aborted -- the in-process pytest
# fixture cannot survive a killed pytest. Downloads sgcollect zips into
# $TESTS_DIR, where teardown's move_artifacts archives them.
#
# Intentionally NOT `set -e`: this is best-effort and must never fail the build.

set -uo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR/../../shared/config.sh"

uv run "$SHARED_PIPELINES_DIR/sg_collect.py" \
    --config "$QE_TESTS_DIR/config.json" \
    --output-dir "$TESTS_DIR" ||
    echo "WARNING: sg_collect.py exited incomplete/non-zero; continuing"
