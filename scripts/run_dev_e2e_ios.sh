#!/usr/bin/env bash
# Run full React Native dev_e2e suite on iOS Simulator.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.nvm/versions/node/v20.20.2/bin:${PATH:-}"
export CBL_NATIVE_WS_RELAUNCH_SCRIPT="${REPO}/scripts/relaunch_ios_app.py"

cd "${REPO}/tests/dev_e2e"
uv run pytest \
  -v \
  -W ignore::DeprecationWarning \
  --config config.json \
  --dataset-version 4.0 \
  --ignore=test_multipeer.py \
  --tb=short \
  --timeout=300 \
  --junitxml=junit_ios.xml \
  "$@"

uv run python "${REPO}/scripts/generate_rn_status_html.py"
