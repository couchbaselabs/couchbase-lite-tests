#!/usr/bin/env bash
# Install the release APK on a connected Android device/emulator and launch it.
# Launch arguments are passed as intent extras so the app auto-connects.
#
# Usage: ./scripts/install-android.sh [device_id] [ws_url]
#   device_id: Device ID for WebSocket registration (default: ws0)
#   ws_url:    WebSocket server URL (default: ws://10.0.2.2:8765)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

DEVICE_ID="${1:-ws0}"
WS_URL="${2:-ws://10.0.2.2:8765}"

APK_PATH="$PROJECT_DIR/android/app/build/outputs/apk/release/app-release.apk"

if [ ! -f "$APK_PATH" ]; then
    echo "APK not found. Building first..."
    "$SCRIPT_DIR/build-android.sh"
fi

echo "=== Installing APK ==="
adb install -r "$APK_PATH"

echo "=== Launching app with auto-connect ==="
adb shell am start \
    -n com.cbltestserver/.MainActivity \
    --es deviceID "$DEVICE_ID" \
    --es wsURL "$WS_URL"

echo "=== Installed and launched ==="
echo "Device ID: $DEVICE_ID"
echo "WebSocket URL: $WS_URL"
echo "The app will auto-connect using the provided launch arguments."
