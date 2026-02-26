#!/bin/bash
set -eu -o pipefail

echo "Checking..."
uv run --group lint ty check
