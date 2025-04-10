#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

export PYTHONPATH=$SCRIPT_DIR/../../../
pushd $SCRIPT_DIR/../../../environment/aws
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 ./stop_backend.py --topology topology_setup/topology.json