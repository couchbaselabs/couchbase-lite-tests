#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

echo "Tearing down multiplatform test environment..."

# Teardown AWS backend resources (SGW and CBS)
echo "Stopping AWS backend resources..."
export PYTHONPATH=$SCRIPT_DIR/../../../
pushd $AWS_ENVIRONMENT_DIR
create_venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 ./stop_backend.py
deactivate
popd

echo "Multiplatform teardown complete." 