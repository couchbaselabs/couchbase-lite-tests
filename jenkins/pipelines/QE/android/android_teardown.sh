#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
export PATH="/opt/homebrew/opt/coreutils/libexec/gnubin:/opt/homebrew/bin:$PATH"
source $SCRIPT_DIR/../../shared/config.sh

pushd $AWS_ENVIRONMENT_DIR
move_artifacts

uv run ./stop_backend.py --topology topology_setup/topology.json
