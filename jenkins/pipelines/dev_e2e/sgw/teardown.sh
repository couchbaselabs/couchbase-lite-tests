#!/bin/bash

# Tears down everything test.sh started: the Sync Gateway process, the local
# CBL-C test server, and the Couchbase Server Docker container. Also collects
# test artifacts. Runs even on failure (Jenkinsfile post { always { ... } }).

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source "$SCRIPT_DIR/../../shared/config.sh"

LOCAL_DIR="$ENVIRONMENT_DIR/local"
DOCKER_DIR="$ENVIRONMENT_DIR/docker"
REPO_ROOT=$(dirname "$ENVIRONMENT_DIR")

# Collect artifacts first (cwd is inside dev_e2e so move_artifacts resolves
# tests/dev_e2e as the source directory).
pushd "$SCRIPT_DIR" > /dev/null
move_artifacts
popd > /dev/null

# Best-effort teardown: keep going even if a step fails so that the Couchbase
# Server container is always cleaned up.
pushd "$REPO_ROOT" > /dev/null
uv run "$LOCAL_DIR/run_sync_gateway.py" --stop || true
uv run "$LOCAL_DIR/start_local.py" --stop || true
popd > /dev/null

pushd "$DOCKER_DIR" > /dev/null
docker compose down -v || true
popd > /dev/null
