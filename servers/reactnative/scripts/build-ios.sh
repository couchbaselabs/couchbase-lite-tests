#!/usr/bin/env bash
# Build iOS release app for the CBL Test Server React Native app.
# The release build embeds the JS bundle so Metro is not required at runtime.
#
# Usage: ./scripts/build-ios.sh
# Requires: macOS, Xcode, CocoaPods, valid signing certificates

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Installing npm dependencies ==="
npm install

echo "=== Installing CocoaPods ==="
cd ios
pod install
cd ..

echo "=== Building iOS release app for device ==="
xcodebuild \
    -workspace ios/CblTestServer.xcworkspace \
    -scheme CblTestServer \
    -sdk iphoneos \
    -configuration Release \
    -derivedDataPath ios/build \
    -allowProvisioningUpdates

APP_PATH="ios/build/Build/Products/Release-iphoneos/CblTestServer.app"
if [ -d "$APP_PATH" ]; then
    echo "=== Build successful ==="
    echo "App: $PROJECT_DIR/$APP_PATH"
else
    echo "=== Build failed: .app bundle not found ==="
    exit 1
fi
