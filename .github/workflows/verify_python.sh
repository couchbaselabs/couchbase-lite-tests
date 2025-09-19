#!/bin/bash
set -eu -o pipefail

VENV_DIR=".venv-typing"

function create_venv() {
    uv venv ${VENV_DIR}
    source ./${VENV_DIR}/bin/activate
}

function cleanup_venv() {
    deactivate
    rm -rf ${VENV_DIR}
}

create_venv
uv pip install "./client[dev]"
echo "Checking client files (including smoke tests)..."
${VENV_DIR}/bin/python -m mypy client
echo "Checking tests files..."
python -m mypy tests --explicit-package-bases
cleanup_venv

create_venv
uv pip install -r ./environment/aws/requirements.txt
echo "Checking environment setup..."
python -m mypy environment --explicit-package-bases
cleanup_venv

create_venv
uv pip install -r jenkins/pipelines/requirements.txt
echo "Checking Jenkins pipelines..."
python -m mypy jenkins --explicit-package-bases
cleanup_venv
