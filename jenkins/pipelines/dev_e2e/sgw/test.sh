#!/bin/bash

# Runs the dev_e2e test suite against a locally provisioned backend:
#   - Couchbase Server in Docker (reuses environment/docker)
#   - Sync Gateway built from source at the given git ref (the PR under test)
#   - A local CBL-C test server (latest released build)
#
# Designed to be runnable both in Jenkins and locally. See
# jenkins/pipelines/dev_e2e/sgw/Jenkinsfile for the CI wrapper.

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

function usage() {
    echo "Usage: $0 <sgw_ref>"
    echo "  <sgw_ref>: Sync Gateway git ref (branch/tag/commit) to build from source."
    exit 1
}

if [ "$#" -ne 1 ]; then usage; fi

SGW_REF=${1}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source "$SCRIPT_DIR/../../shared/config.sh"

REPO_ROOT=$(dirname "$ENVIRONMENT_DIR")
LOCAL_DIR="$ENVIRONMENT_DIR/local"
DOCKER_DIR="$ENVIRONMENT_DIR/docker"

# 1. Start Couchbase Server (only the CBS service from the docker environment).
#    configure-node.sh inside the container performs cluster-init with the
#    Administrator/password credentials that Sync Gateway and the test
#    framework expect.
echo "Starting Couchbase Server..."
pushd "$DOCKER_DIR" > /dev/null
docker compose up -d cbl-test-cbs
popd > /dev/null

echo "Waiting for Couchbase Server to finish cluster initialization..."
for _ in $(seq 1 90); do
    status=$(curl -s -o /dev/null -w "%{http_code}" -u Administrator:password \
        http://localhost:8091/pools/default || true)
    if [ "$status" = "200" ]; then
        echo "Couchbase Server is ready."
        break
    fi
    sleep 2
done
if [ "${status:-}" != "200" ]; then
    echo "Couchbase Server did not become ready in time." >&2
    exit 1
fi

# 2. Build Sync Gateway from source at the requested ref.
echo "Building Sync Gateway from ref '$SGW_REF'..."
pushd "$REPO_ROOT" > /dev/null
uv run "$LOCAL_DIR/build_sync_gateway.py" --git-tag "$SGW_REF"

# 3. Run Sync Gateway against Couchbase Server.
echo "Starting Sync Gateway against Couchbase Server..."
uv run "$LOCAL_DIR/run_sync_gateway.py" --start --server cbs

# 4. Start the local CBL-C test server (latest released build).
echo "Starting CBL-C test server..."
uv run "$LOCAL_DIR/start_local.py"
popd > /dev/null

# 5. Run the dev_e2e suite. Tests requiring resources the local backend does
#    not provide (e.g. the 2-CBS + load-balancer XDCR test) skip themselves
#    via their @pytest.mark.min_* markers.
echo "Running dev_e2e tests..."
pushd "$DEV_E2E_TESTS_DIR" > /dev/null
uv run pytest -v --no-header -W ignore::DeprecationWarning \
    --config "$LOCAL_DIR/cbs_config.json"
popd > /dev/null
