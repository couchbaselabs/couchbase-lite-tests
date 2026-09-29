#!/usr/bin/env bash
# Build Android release APK for the CBL Test Server React Native app.
# The release build embeds the JS bundle so Metro is not required at runtime.
#
# Usage: ./scripts/build-android.sh
# Output: android/app/build/outputs/apk/release/app-release.apk

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Installing npm dependencies ==="
npm install

echo "=== Building Android release APK ==="
cd android
./gradlew assembleRelease

APK_PATH="app/build/outputs/apk/release/app-release.apk"
if [ -f "$APK_PATH" ]; then
    echo "=== Build successful ==="
    echo "APK: $PROJECT_DIR/android/$APK_PATH"
else
    echo "=== Build failed: APK not found ==="
    exit 1
fi
