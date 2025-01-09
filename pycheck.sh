#!/bin/bash -e

rm -rf smoke-test-venv
python3.10 -m venv smoke-test-venv
source smoke-test-venv/bin/activate
pip install mypy
pip install pytest pytest-asyncio
pip install ruff
pip install types-requests types-deprecated
pip install ./client
echo "Checking client files (including smoke tests)..."
python -m mypy client --exclude=venv
echo "Checking tests files..."
python -m mypy tests --exclude=venv
echo "Checking format of code"
ruff format
echo "Checking lint of code"
ruff check --fix
rm -rf smoke-test-venv
