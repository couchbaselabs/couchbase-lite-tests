#!/bin/bash -e

python3 -m venv venv
source venv/bin/activate
pip install mypy
pip install pytest
pip install types-requests
pip install types-Deprecated
pip install ./client
echo "Checking tests files..."
python -m mypy tests --exclude=venv --ignore-missing-imports
echo "Checking client files (including smoke tests)..."
python -m mypy client --exclude=venv --ignore-missing-imports
deactivate
rm -rf venv
