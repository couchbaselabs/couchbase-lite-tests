# Couchbase Lite Test Server for React Native

A WebSocket-based test server for the [cbl-reactnative](https://github.com/Couchbase-Ecosystem/cbl-reactnative) SDK, following the same protocol as `servers/javascript/`.

## Architecture

```
Python Tests (pytest)
    ↕ WebSocket
React Native App (this server)
    ↕ NativeModules bridge
Couchbase Lite Enterprise 3.3.0 (iOS/Android native)
    ↕ replication
Couchbase Server + Sync Gateway (Docker)
```

The app connects **out** to the Python client's WebSocket server (device is the WS client, Python is the WS server), sends a Hello message with its device ID, then processes commands and returns responses.

## Prerequisites

- Node.js >= 18
- React Native CLI (`npx react-native`)
- For Android: Android SDK, JDK 17, connected device or emulator
- For iOS: macOS, Xcode 15+, CocoaPods

## Setup

```bash
cd servers/reactnative
npm install

# iOS only:
cd ios && pod install && cd ..
```

## Build

```bash
# Android debug APK
./scripts/build-android.sh

# iOS debug build
./scripts/build-ios.sh
```

## Run

```bash
# Start Metro bundler
npx react-native start

# Run on Android
npx react-native run-android

# Run on iOS
npx react-native run-ios
```

## Usage

### Automated (CI / Launch Arguments)

The app supports **auto-connect via launch arguments**, eliminating manual interaction. Pass `deviceID` and `wsURL` when launching the app and it will connect automatically, retrying up to 30 times (2 s interval) if the WebSocket server isn't ready yet.

**Android (adb):**

```bash
adb shell am start \
    -n com.cbltestserver/.MainActivity \
    --es deviceID "ws0" \
    --es wsURL "ws://10.0.2.2:8765"
```

**iOS Simulator (xcrun):**

```bash
xcrun simctl launch booted com.cbltestserver \
    -deviceID "ws0" \
    -wsURL "ws://localhost:8765"
```

The helper script `scripts/install-android.sh` wraps the install + launch with auto-connect:

```bash
./scripts/install-android.sh ws0 ws://10.0.2.2:8765
```

### Manual

1. Launch the app on the device/emulator
2. Enter the device ID (e.g., `ws0`)
3. Enter the WebSocket URL of the Python test client (e.g., `ws://10.0.2.2:8765` for Android emulator, or `ws://<host-ip>:8765` for physical device)
4. Tap **Connect**
5. The app will register with the Python test client and begin processing test commands

If no launch arguments are provided, the app starts in manual mode as before.

## Configuration

In the test config JSON, add the server entry with WebSocket transport:

```json
{
  "test-servers": [
    {
      "url": "ws://device-ip:8080",
      "transport": "ws"
    }
  ]
}
```

## Supported Endpoints

| Endpoint | Status |
|----------|--------|
| `/` (getInfo) | Supported |
| `/newSession` | Supported |
| `/reset` | Supported (with dataset loading) |
| `/getAllDocuments` | Supported (via SQL++ query) |
| `/getDocument` | Supported |
| `/updateDatabase` | Supported |
| `/startReplicator` | Partial (no filters/conflict resolvers) |
| `/stopReplicator` | Supported |
| `/getReplicatorStatus` | Supported |
| `/snapshotDocuments` | Supported |
| `/verifyDocuments` | Supported |
| `/performMaintenance` | Supported |
| `/runQuery` | Supported |
| `/log` | Supported |
| `/startListener` | Not supported (501) |
| `/stopListener` | Not supported (501) |
| `/startMultipeerReplicator` | Not supported (501) |
| `/stopMultipeerReplicator` | Not supported (501) |
| `/getMultipeerReplicatorStatus` | Not supported (501) |

## Limitations

- **Replication filters**: The cbl-reactnative bridge does not support JavaScript callback functions for push/pull filters. Tests requiring custom filters will fail.
- **Conflict resolvers**: Same limitation as filters. The bridge passes a serialized config but cannot marshal JS functions to native.
- **URLEndpointListener**: Not implemented in cbl-reactnative.
- **Multipeer replication**: Not implemented in cbl-reactnative.
- **Performance**: All SDK calls cross the RN bridge (JS → Native), which adds latency. Large batch operations will be slower than native servers.
