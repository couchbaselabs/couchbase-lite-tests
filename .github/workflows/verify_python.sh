#!/bin/bash -e

python3 -m venv venv
source ./venv/bin/activate
pip install mypy
pip install pytest pytest-asyncio
pip install types-requests types-Deprecated types-tqdm types-paramiko
pip install ./client
echo "Checking tests files..."
python -m mypy tests --exclude=venv
echo "Checking client files (including smoke tests)..."
python -m mypy client --exclude=venv
echo "Checking environment setup..."
python -m mypy environment --exclude=venv
deactivate
rm -rf venv
