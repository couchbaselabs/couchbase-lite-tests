#!/bin/bash

set -euo pipefail

if [[ "$(uname)" == "Darwin" ]]; then
    export MD_APPLE_SDK_ROOT="/$(echo "$(xcode-select -p)" | cut -d'/' -f2-3)"
fi

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../shared/config.sh
pushd $AWS_ENVIRONMENT_DIR
move_artifacts

uv run ./stop_backend.py --topology topology_setup/topology.json
