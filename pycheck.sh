#!/bin/bash -e

rm -rf smoke-test-venv
python3.10 -m venv smoke-test-venv
source smoke-test-venv/bin/activate
pip install mypy
pip install pytest
pip install types-requests
pip install ./client
echo "Checking client files (including smoke tests)..."
python -m mypy client --exclude=venv --ignore-missing-imports
echo "Checking tests files..."
python -m mypy tests --exclude=venv --ignore-missing-imports
rm -rf smoke-test-venv

