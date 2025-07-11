#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/../../../shared/config.sh

export PYTHONPATH=$SCRIPT_DIR/../../../
pushd $AWS_ENVIRONMENT_DIR
move_artifacts

stop_venv
create_venv venv
source venv/bin/activate
trap stop_venv EXIT
pip install -r requirements.txt
python3 ./stop_backend.py --topology topology_setup/topology.json
popd