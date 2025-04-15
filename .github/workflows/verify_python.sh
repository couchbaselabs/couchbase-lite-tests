#!/bin/bash -e

python3 -m venv venv
source ./venv/bin/activate
pip install --upgrade pip
pip install mypy
pip install pytest pytest-asyncio
pip install types-requests types-Deprecated types-tqdm types-paramiko types-netifaces types-psutil click
pip install ./client
echo "Checking tests files..."
python -m mypy tests --exclude=venv
echo "Checking client files (including smoke tests)..."
python -m mypy client --exclude=venv
echo "Checking environment setup..."
python -m mypy environment --exclude=venv --explicit-package-bases --check-untyped-defs
echo "Checking Jenkins pipelines..."
python -m mypy jenkins --exclude=venv --explicit-package-bases
deactivate
rm -rf venv
