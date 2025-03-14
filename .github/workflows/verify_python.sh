#!/bin/bash -e

python3 -m venv venv
source ./venv/bin/activate
pip install mypy
pip install pytest pytest-asyncio
pip install types-requests types-Deprecated types-tqdm types-paramiko types-netifaces types-psutil
pip install ./client
echo "Checking tests files..."
python -m mypy tests --exclude=venv --explicit-package-bases --check-untyped-defs
echo "Checking client files (including smoke tests)..."
python -m mypy client --exclude=venv --explicit-package-bases --check-untyped-defs
echo "Checking environment setup..."
python -m mypy environment --exclude=venv --explicit-package-bases --check-untyped-defs
deactivate
rm -rf venv
