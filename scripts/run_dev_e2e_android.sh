#!/usr/bin/env bash
# Run full React Native dev_e2e suite on Android emulator.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.nvm/versions/node/v20.20.2/bin:${HOME}/Library/Android/sdk/platform-tools:${PATH:-}"
export CBL_NATIVE_WS_RELAUNCH_SCRIPT="${REPO}/scripts/relaunch_android_app.py"

# Stop iOS simulator app to avoid WS port conflicts
xcrun simctl terminate 793881A3-248F-4AB1-A26B-6D581917BF0E com.cbltestserver 2>/dev/null || true

adb -s emulator-5554 reverse tcp:8765 tcp:8765
adb -s emulator-5554 reverse tcp:4984 tcp:4984
adb -s emulator-5554 shell am force-stop com.cbltestserver

cd "${REPO}/tests/dev_e2e"
uv run pytest \
  -v \
  -W ignore::DeprecationWarning \
  --config config.json \
  --dataset-version 4.0 \
  --ignore=test_multipeer.py \
  --tb=short \
  --timeout=300 \
  --junitxml=junit_android.xml \
  "$@"

uv run python "${REPO}/scripts/generate_rn_status_html.py"
