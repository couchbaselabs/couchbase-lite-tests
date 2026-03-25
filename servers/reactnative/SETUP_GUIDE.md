# React Native Test Server -- Complete iOS Setup Guide

## 1. Overview

This guide walks you through setting up and running the Couchbase Lite React Native test server on an iOS Simulator, from scratch.

### Architecture

```
Python Tests (pytest)          ← test runner, drives everything
    ↕ WebSocket (port 8765)
React Native App (this server) ← runs on iOS Simulator
    ↕ NativeModules bridge
Couchbase Lite Enterprise      ← native Swift SDK (via cbl-reactnative)
    ↕ replication
Couchbase Server + Sync Gateway ← Docker containers on your Mac
```

**How it works:**

1. `pytest` starts a WebSocket server on port 8765.
2. The React Native app (WS *client*) connects to that server and sends a "hello" with its device ID.
3. pytest sends test commands (reset DB, start replicator, run query, etc.) over the WebSocket.
4. The app executes each command via the native Couchbase Lite SDK and returns results.
5. pytest asserts the results.

---

## 2. Prerequisites

Install the following on your Mac before proceeding.

### 2.1 Homebrew

If you don't have Homebrew:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2.2 Xcode

- Install **Xcode 15+** (16.2 recommended) from the Mac App Store or [developer.apple.com](https://developer.apple.com/xcode/).
- After installing, open Xcode once to accept the license and install components.
- Install Command Line Tools:

```bash
xcode-select --install
```

- Verify:

```bash
xcodebuild -version
# Expected: Xcode 16.x, Build version ...
```

### 2.3 Node.js (>= 18)

```bash
brew install node@18
```

Verify:

```bash
node --version
# Expected: v18.x.x or v20.x.x (v22+ may cause Metro bundler issues)
```

### 2.4 Python (3.10 -- 3.13)

Python 3.14 is **not** supported (the `couchbase` SDK lacks wheels for it).

```bash
brew install python@3.13
```

Verify:

```bash
python3 --version
# Expected: Python 3.10.x through 3.13.x
```

### 2.5 Docker Desktop

- Download and install from [docker.com](https://www.docker.com/products/docker-desktop/).
- Launch Docker Desktop and ensure the whale icon appears in your menu bar.

### 2.6 CocoaPods

```bash
sudo gem install cocoapods
```

Verify:

```bash
pod --version
```

### 2.7 Git LFS

```bash
brew install git-lfs
git lfs install
```

---

## 3. Clone and Bootstrap the Repository

### 3.1 Clone

```bash
git clone https://github.com/couchbaselabs/couchbase-lite-tests.git
cd couchbase-lite-tests
```

### 3.2 Pull LFS Data

Test datasets (JSON docs, blob images) are stored in Git LFS. You **must** pull them or tests will fail.

```bash
git lfs pull
```

### 3.3 Create a Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3.4 Install the Python Test Client

```bash
pip install -e client/
```

This installs the `cbltest` pytest plugin and all its dependencies (`aiohttp`, `pytest`, `websocket-client`, `couchbase`, `cryptography`, etc.).

---

## 4. Start the Docker Backend

The backend provides **Couchbase Server 7.6.4** and **Sync Gateway 3.2.0** running in Docker containers. This is required -- the tests replicate data between the React Native app and these services.

### 4.1 Increase Docker Resources

Open **Docker Desktop → Settings → Resources** and set:

- **Memory:** 8 GB (minimum)
- **Disk:** 80 GB (minimum)

Click "Apply & Restart".

### 4.2 Start the Containers

```bash
cd environment/docker
docker compose up -d
```

This builds and starts three containers:

| Container | Purpose | Ports |
|-----------|---------|-------|
| `cbl-test-cbs` | Couchbase Server | 8091, 11210, etc. |
| `cbl-test-sg` | Sync Gateway (with SSL) | 4984, 4985 |
| `cbl-test-logslurp` | Log aggregator | 8180 |

### 4.3 Wait for Readiness

Run the helper script:

```bash
python3 start_environment.py
```

This polls Docker logs until Sync Gateway prints "Sync Gateway is up". It usually takes 30--60 seconds.

**Alternatively**, check manually:

```bash
# Couchbase Server: open in browser
open http://localhost:8091
# Login: Administrator / password

# Sync Gateway: check logs
docker compose logs -f cbl-test-sg
# Wait until you see: "Sync Gateway is up"
```

### 4.4 Return to Repo Root

```bash
cd ../..
```

### 4.5 Credentials Reference

| Service | Username | Password |
|---------|----------|----------|
| Couchbase Server (Web UI & RBAC) | `Administrator` | `password` |
| Sync Gateway (REST Admin API) | `admin` | `password` |

---

## 5. Build the React Native App for iOS Simulator

### 5.1 Install npm Dependencies

```bash
cd servers/reactnative
npm install
```

### 5.2 Install CocoaPods Dependencies

```bash
cd ios
pod install
cd ..
```

### 5.3 Build the Offline JavaScript Bundle

The Metro bundler can be problematic with Node.js v22+. Building an offline bundle avoids this entirely and is the recommended approach.

```bash
npx react-native bundle \
  --platform ios \
  --dev false \
  --entry-file index.js \
  --bundle-output ios/main.jsbundle \
  --assets-dest ios
```

This creates `ios/main.jsbundle`. The app's `AppDelegate.mm` is configured to load this embedded bundle instead of connecting to a live Metro server.

### 5.4 Build the iOS App with Xcode

```bash
cd ios
xcodebuild \
  -workspace CblTestServer.xcworkspace \
  -scheme CblTestServer \
  -configuration Debug \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro' \
  build
cd ..
```

The build takes 2--5 minutes the first time (subsequent builds are faster).

### 5.5 Return to Repo Root

```bash
cd ../..
```

### Troubleshooting

**Swift compatibility errors (`__swift_FORCE_LOAD_$_swiftCompatibility56`):**

If you have multiple Xcode versions installed, explicitly set the one you want:

```bash
export DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer"
```

Then retry the build.

**Xcode database locked errors:**

Clean derived data and retry:

```bash
rm -rf ~/Library/Developer/Xcode/DerivedData/CblTestServer-*
```

**Build succeeds but app crashes on launch:**

Ensure you built the JS bundle (Step 5.3) before building the Xcode project. The app loads `main.jsbundle` from the app bundle -- if it's missing, the app will crash.

---

## 6. Install the App on the iOS Simulator

### 6.1 Boot a Simulator

```bash
xcrun simctl boot "iPhone 16 Pro"
```

If it's already booted, this will print an error -- that's fine, ignore it.

You can also open the Simulator app manually: **Xcode → Open Developer Tool → Simulator**.

### 6.2 Find the Built App

The built `.app` bundle lives inside Xcode's DerivedData:

```bash
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/CblTestServer-*/Build/Products/Debug-iphonesimulator -name "CblTestServer.app" -maxdepth 1 | head -1)
echo "App path: $APP_PATH"
```

### 6.3 Install the App

```bash
xcrun simctl install booted "$APP_PATH"
```

### 6.4 Verify Installation

```bash
xcrun simctl listapps booted | grep com.cbltestserver
```

You should see an entry for `com.cbltestserver`.

---

## 7. Create the Test Config File

The config file tells pytest where to find the Docker backend and the test server.

Create `environment/aws/config.json`:

```json
{
  "couchbase-servers": [
    {
      "hostname": "localhost"
    }
  ],
  "sync-gateways": [
    {
      "hostname": "localhost",
      "rbac_user": "Administrator",
      "rbac_password": "password",
      "tls": true
    }
  ],
  "test-servers": [
    {
      "url": "ws://localhost:8765",
      "transport": "ws"
    }
  ]
}
```

### Field Explanations

| Field | Value | Why |
|-------|-------|-----|
| `couchbase-servers[].hostname` | `localhost` | CBS Docker container is on your Mac |
| `sync-gateways[].hostname` | `localhost` | SG Docker container is on your Mac |
| `sync-gateways[].rbac_user` | `Administrator` | CBS admin user that SG uses |
| `sync-gateways[].rbac_password` | `password` | CBS admin password |
| `sync-gateways[].tls` | `true` | Docker SG is configured with SSL enabled |
| `test-servers[].url` | `ws://localhost:8765` | Python starts a WS server here; the RN app connects to it |
| `test-servers[].transport` | `ws` | Tells pytest to use WebSocket transport (not HTTP) |

---

## 8. Run the dev_e2e Tests

Running tests requires two coordinated steps: starting pytest (which creates the WS server) and launching the app (which connects to it).

### 8.1 Activate the Virtual Environment

```bash
cd /path/to/couchbase-lite-tests
source .venv/bin/activate
```

### 8.2 Start the Test Suite

Run pytest in the background, redirecting output to a log file:

```bash
python -m pytest tests/dev_e2e/ \
  --config environment/aws/config.json \
  -v \
  --timeout=120 \
  --ignore=tests/dev_e2e/test_multipeer.py \
  -k "not listener and not multipeer and not filter and not custom_conflict" \
  --tb=short \
  2>&1 | tee /tmp/rn_test_results.log &
```

pytest will:
1. Start a WebSocket server on port 8765.
2. Wait up to 30 seconds for the React Native app to connect.
3. Begin sending test commands once connected.

### 8.3 Wait for the WebSocket Server

Give pytest a moment to start listening:

```bash
sleep 2

# Verify it's listening
lsof -i :8765 | grep LISTEN
```

### 8.4 Launch the React Native App

Terminate any previously running instance, then launch with auto-connect arguments:

```bash
xcrun simctl terminate booted com.cbltestserver 2>/dev/null || true

xcrun simctl launch booted com.cbltestserver \
  -deviceID "ws0" \
  -wsURL "ws://localhost:8765"
```

**Launch arguments explained:**

| Argument | Value | Purpose |
|----------|-------|---------|
| `-deviceID` | `ws0` | Identifies this device to the Python WS server. The `0` maps to `test-servers[0]` in the config. |
| `-wsURL` | `ws://localhost:8765` | WebSocket URL of the Python test runner. `localhost` works because the simulator shares the Mac's network. |

The app will:
1. Read the launch arguments.
2. Connect to `ws://localhost:8765`.
3. Send a hello message: `{"device": "ws0", "apiVersion": 1}`.
4. Begin processing test commands from pytest.

### 8.5 What Happens Next

pytest runs through all collected tests sequentially. For each test it typically:
1. Sends `/reset` to create/reset databases and load datasets.
2. Sends `/startReplicator` to begin replication with Sync Gateway.
3. Polls `/getReplicatorStatus` until replication completes.
4. Sends `/snapshotDocuments`, `/verifyDocuments`, `/runQuery`, etc. to assert results.
5. Cleans up replicators and databases.

---

## 9. Run Smoke Tests (Quick Sanity Check)

Smoke tests are faster and test individual endpoints in isolation. Good for verifying the setup works before running the full suite.

### 9.1 Start pytest

```bash
source .venv/bin/activate

python -m pytest client/smoke_tests/ \
  --config environment/aws/config.json \
  -v \
  --ignore=client/smoke_tests/test_listener.py \
  --ignore=client/smoke_tests/test_multipeer.py \
  -k "not logslurp" \
  --tb=short \
  2>&1 | tee /tmp/rn_smoke_results.log &
```

### 9.2 Launch the App

```bash
sleep 2
xcrun simctl terminate booted com.cbltestserver 2>/dev/null || true
xcrun simctl launch booted com.cbltestserver \
  -deviceID "ws0" \
  -wsURL "ws://localhost:8765"
```

### 9.3 Check Results

```bash
tail -f /tmp/rn_smoke_results.log
```

---

## 10. Monitor and Interpret Results

### 10.1 Watch Live Output

```bash
tail -f /tmp/rn_test_results.log
```

### 10.2 Read the Summary

After the suite finishes, look for the final summary line:

```
====== 72 passed, 5 failed, 20 skipped in 340.12s ======
```

Or filter for it:

```bash
grep -E "passed|failed|error" /tmp/rn_test_results.log | tail -5
```

### 10.3 Check if Tests Are Still Running

```bash
ps aux | grep pytest | grep -v grep
```

If there's output, tests are still running. If empty, they've finished.

### 10.4 View Only Failures

```bash
grep -A 10 "FAILED" /tmp/rn_test_results.log
```

### 10.5 Run a Single Test

To debug a specific failure:

```bash
# Start pytest with just one test
python -m pytest tests/dev_e2e/test_basic_replication.py::TestBasicReplication::test_push_and_pull \
  --config environment/aws/config.json \
  -v --timeout=120 -s \
  2>&1 | tee /tmp/rn_single_test.log &

# Launch the app
sleep 2
xcrun simctl terminate booted com.cbltestserver 2>/dev/null || true
xcrun simctl launch booted com.cbltestserver -deviceID "ws0" -wsURL "ws://localhost:8765"

# Watch
tail -f /tmp/rn_single_test.log
```

### 10.6 Full Tracebacks

Add `--tb=long` to the pytest command for detailed stack traces on failures.

---

## 11. Known Limitations and Expected Failures

The React Native server does **not** support all features of the native test servers. The following tests will fail or be skipped:

| Feature | Tests Affected | Reason |
|---------|---------------|--------|
| Custom push/pull filters | `test_replication_filter.py` (partially) | JS callback functions cannot cross the RN native bridge |
| Custom conflict resolvers | `test_custom_conflict.py` | Same bridge limitation |
| URLEndpointListener | `test_listener.py` (smoke), listener tests | Not implemented in `cbl-reactnative` (returns 501) |
| Multipeer replication | `test_multipeer.py` | Not implemented in `cbl-reactnative` (returns 501) |
| CBL 4.0 upgrade tests | `test_replication_upgrade.py` | Requires CBL >= 4.0 and working conflict resolvers |

### Recommended Filters

To skip all known-unsupported tests:

```bash
python -m pytest tests/dev_e2e/ \
  --config environment/aws/config.json \
  -v --timeout=300 \
  --ignore=tests/dev_e2e/test_multipeer.py \
  --ignore=tests/dev_e2e/test_custom_conflict.py \
  --ignore=tests/dev_e2e/test_replication_upgrade.py \
  -k "not listener and not multipeer and not filter and not custom_conflict and not filter_removed_access" \
  --tb=short
```

### Expected Results Summary

| Test File | Expected |
|-----------|----------|
| `test_basic_replication.py` | PASS |
| `test_fest.py` | PASS |
| `test_query_consistency.py` | PASS |
| `test_replication_behavior.py` | PASS |
| `test_replication_blob.py` | PASS |
| `test_replication_xdcr.py` | PASS |
| `test_replication_auto_purge.py` | MIXED (most pass; `filter_removed_access` fails) |
| `test_replication_filter.py` | MIXED (channel/docID filters pass; custom callbacks fail) |
| `test_encrypted_properties.py` | SKIP (C platform only) |
| `test_custom_conflict.py` | FAIL |
| `test_replication_upgrade.py` | FAIL |
| `test_multipeer.py` | SKIP |

---

## 12. Teardown and Cleanup

### 12.1 Stop the React Native App

```bash
xcrun simctl terminate booted com.cbltestserver
```

### 12.2 Stop Docker Containers

```bash
cd environment/docker

# Stop containers (keeps images for fast restart)
docker compose down

# OR: Stop and remove everything (images, volumes)
docker compose down --rmi all -v
```

### 12.3 Deactivate the Python Virtual Environment

```bash
deactivate
```

### 12.4 Kill Any Lingering Processes

```bash
# Kill any leftover pytest or WS server
kill $(lsof -ti :8765) 2>/dev/null || true
```

---

## 13. Quick Reference -- Full Copy-Paste Script

A single end-to-end sequence from zero to running tests. Copy and run block by block.

```bash
# ──────────────────────────────────────────────
# STEP 1: Docker Backend
# ──────────────────────────────────────────────
cd /path/to/couchbase-lite-tests
cd environment/docker
docker compose up -d
python3 start_environment.py
cd ../..

# ──────────────────────────────────────────────
# STEP 2: Python Environment
# ──────────────────────────────────────────────
python3 -m venv .venv
source .venv/bin/activate
pip install -e client/
git lfs pull

# ──────────────────────────────────────────────
# STEP 3: Build React Native App
# ──────────────────────────────────────────────
cd servers/reactnative
npm install
cd ios && pod install && cd ..

npx react-native bundle \
  --platform ios --dev false \
  --entry-file index.js \
  --bundle-output ios/main.jsbundle \
  --assets-dest ios

cd ios
xcodebuild \
  -workspace CblTestServer.xcworkspace \
  -scheme CblTestServer \
  -configuration Debug \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro' \
  build
cd ../..

# ──────────────────────────────────────────────
# STEP 4: Install on Simulator
# ──────────────────────────────────────────────
xcrun simctl boot "iPhone 16 Pro" 2>/dev/null || true
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/CblTestServer-*/Build/Products/Debug-iphonesimulator -name "CblTestServer.app" -maxdepth 1 | head -1)
xcrun simctl install booted "$APP_PATH"

# ──────────────────────────────────────────────
# STEP 5: Create Config
# ──────────────────────────────────────────────
cat > environment/aws/config.json << 'EOF'
{
  "couchbase-servers": [{ "hostname": "localhost" }],
  "sync-gateways": [{
    "hostname": "localhost",
    "rbac_user": "Administrator",
    "rbac_password": "password",
    "tls": true
  }],
  "test-servers": [{
    "url": "ws://localhost:8765",
    "transport": "ws"
  }]
}
EOF

# ──────────────────────────────────────────────
# STEP 6: Run Tests
# ──────────────────────────────────────────────
source .venv/bin/activate

python -m pytest tests/dev_e2e/ \
  --config environment/aws/config.json \
  -v --timeout=120 \
  --ignore=tests/dev_e2e/test_multipeer.py \
  -k "not listener and not multipeer and not filter and not custom_conflict" \
  --tb=short \
  2>&1 | tee /tmp/rn_test_results.log &

sleep 2
xcrun simctl terminate booted com.cbltestserver 2>/dev/null || true
xcrun simctl launch booted com.cbltestserver \
  -deviceID "ws0" -wsURL "ws://localhost:8765"

# ──────────────────────────────────────────────
# STEP 7: Monitor
# ──────────────────────────────────────────────
tail -f /tmp/rn_test_results.log
```
