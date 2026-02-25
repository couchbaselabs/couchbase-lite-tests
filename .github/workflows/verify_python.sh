#!/bin/bash
set -eu -o pipefail

echo "Checking..."
uv run --group orchestrator-lint ty check
