# Platform Test Servers — `servers/`

Per-platform test server implementations. Each one implements the same REST API (defined in [spec/api/api.yaml](../spec/api/api.yaml)) in the native language for its platform, so the Python `cbltest` framework can drive Couchbase Lite operations uniformly.

## Scope

You own everything under `servers/`:

| Path | Language | Build System | Target Platforms | Transport |
|---|---|---|---|---|
| `c/` | C++ (C++17) | CMake 3.23+ | macOS, Linux, Windows, iOS, Android | HTTP (CivetWeb) |
| `dotnet/` | C# (.NET MAUI + .NET CLI; `net10.0-{ios,maccatalyst,android}` and `net8.0`) | MSBuild / `dotnet` CLI | iOS, Mac Catalyst, Android via MAUI test server; desktop/CLI via `net8.0` CLI server | HTTP (Kestrel) |
| `ios/` | Swift | Xcode | iOS device + simulator | HTTP |
| `jak/` | Java / Kotlin | Gradle | Android, JVM Desktop, Web Service | HTTP |
| `javascript/` | TypeScript | Vite / Vitest | Browser | **WebSocket** (not HTTP) |

You do **not** own the API spec (`spec/`), the framework (`client/`), or the tests (`tests/`), but you understand how they consume your server implementations.

## Shared Architecture

Every server implements the same layered shape:

```
HTTP / WS Listener → Router / Dispatcher → Handlers (one per endpoint) → CBL SDK Wrapper → Session Manager
```

## API Endpoints (19, defined in `spec/api/api.yaml`)

Every server MUST implement every endpoint.

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Server info: API version, server UUID, CBL version, platform |
| `/newSession` | POST | Create a test session |
| `/reset` | POST | Reset databases (create, load dataset, or delete) |
| `/getAllDocuments` | POST | List document IDs in collections |
| `/updateDatabase` | POST | CRUD on documents |
| `/startReplicator` | POST | Start a replication session |
| `/stopReplicator` | POST | Stop a running replication session |
| `/getReplicatorStatus` | POST | Get replicator status / activity |
| `/snapshotDocuments` | POST | Snapshot document state |
| `/verifyDocuments` | POST | Verify documents against a snapshot |
| `/performMaintenance` | POST | Compact, integrity check, … |
| `/runQuery` | POST | Execute N1QL queries |
| `/getDocument` | POST | Get a single document by ID |
| `/log` | POST | Write to server-side log |
| `/startListener` | POST | Start a P2P passive listener |
| `/stopListener` | POST | Stop a P2P passive listener |
| `/startMultipeerReplicator` | POST | Start multipeer mesh replication |
| `/stopMultipeerReplicator` | POST | Stop multipeer mesh replication |
| `/getMultipeerReplicatorStatus` | POST | Multipeer replicator status |

Required request headers: `CBLTest-API-Version` (int), `CBLTest-Client-ID` (UUID).
Required response headers: `CBLTest-API-Version`, `CBLTest-Server-ID`.

## Per-Platform Layout

### C (`c/`)

```
c/
├── CMakeLists.txt
├── scripts/                    # download_cbl.sh + build_{macos,linux,ios,android}.sh + build_wins.ps1
├── src/
│   ├── TestServer.{h,cpp}      # CivetWeb-based HTTP server
│   ├── Dispatcher.{h,cpp}      # Route dispatcher
│   ├── dispatcher/             # One .cpp per endpoint (GetRoot.cpp, PostReset.cpp, …)
│   ├── cbl/                    # CBL wrappers (CBLManager, Snapshot, Fleece)
│   ├── Session.h
│   └── main.cpp
├── vendor/                     # CivetWeb, nlohmann/json
├── lib/                        # CBL SDK (downloaded)
└── platforms/                  # iOS / Android build configs
```

Build: `./scripts/build_macos.sh <version> <build_num>` → `build/out/bin/`

### .NET (`dotnet/`)

```
dotnet/
├── testserver.sln
├── testserver/                 # ASP.NET web host (iOS, Android, macOS targets)
├── testserver.cli/             # CLI entry (Windows)
├── testserver.logic/
│   ├── Handlers/               # One .cs per endpoint (GetRootHandler.cs, ResetDatabaseHandler.cs, …)
│   ├── Services/
│   ├── Router.cs
│   └── TestServer.cs
└── scripts/                    # legacy helper scripts (not the build path)
```

Build: via the orchestrator — `dotnet_register.py::build()` runs `dotnet publish` (after pinning the `Couchbase.Lite.Enterprise` package version). There is no standalone build script.

### iOS (`ios/`)

```
ios/
├── TestServer.xcodeproj/
├── TestServer/
│   ├── Handlers/               # One .swift per endpoint
│   ├── Server/                 # HTTP server
│   ├── Middleware/, ContentTypes/, Utils/
├── Scripts/                    # build.sh, download_cbl.sh, gen_cbl_version.sh
└── Frameworks/                 # CouchbaseLiteSwift.xcframework (downloaded)
```

Build: `./Scripts/build.sh <type> <edition> <version> <build_num>` → `.app` in `build/`

### JVM / Kotlin (`jak/`)

```
jak/
├── version.txt
├── shared/
│   ├── common/main/java/.../endpoints/v1/   # Handler classes (GetAllDocs, UpdateDb, RunQuery, …)
│   ├── jvm/                                 # BaseTestApp, PlatformDispatcher
│   └── server/                              # HTTP server
├── android/                    # Android app variant
├── desktop/                    # Desktop JVM variant
└── webservice/                 # Web service variant
```

Build: `cd <variant> && ./gradlew build`

### JavaScript (`javascript/`)

```
javascript/
├── package.json                # @couchbase/test-server
├── tsconfig.json
├── vite.config.js
├── eslint.config.mjs
└── src/
    ├── testServer.ts           # Main server (WebSocket)
    ├── tdk.ts
    ├── tdkSchema.ts
    ├── snapshot.ts, filters.ts, conflictResolvers.ts, keyPath.ts
    ├── utils.ts
    └── webSocketClient.ts      # WebSocket transport
```

Build: `npm install && npm run dev`.
**Note:** JS uses **WebSocket** instead of HTTP. The framework handles this via `client/src/cbltest/websocket_router.py`. A `Hello` handshake message replaces HTTP headers for API version + server ID.

## Build Script Pattern (every platform)

1. **Download CBL SDK** — `download_cbl.sh` / `download_cbl.ps1`
   - Release: `https://packages.couchbase.com/releases/couchbase-lite-{platform}/{version}/…`
   - CI: `http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-{platform}/{version}/{build_num}/…`
2. **Build** — `cmake`, `dotnet publish`, `xcodebuild`, `gradle`, `vite`
3. **Copy assets** — datasets, dynamic libraries
4. **Package** — output in `build/` or `out/`

Scripts must support both release URLs (`BLD_NUM=0`) and CI URLs.

## Handler Cross-Reference

When adding a new endpoint, **every** platform must be updated. Examples:

| Endpoint | C (`dispatcher/`) | .NET (`Handlers/`) | Swift (`Handlers/`) | JVM (`endpoints/v1/`) | JS (`src/`) |
|---|---|---|---|---|---|
| GET `/` | `GetRoot.cpp` | `GetRootHandler.cs` | `GetRootHandler.swift` | `TestApp.java` | `testServer.ts` |
| POST `/reset` | `PostReset.cpp` | `ResetDatabaseHandler.cs` | `ResetHandler.swift` | `Session.java` | `tdk.ts` |
| POST `/startReplicator` | `PostStartReplicator.cpp` | `StartReplicatorHandler.cs` | `StartReplicator.swift` | `ReplicatorManager.java` | `tdk.ts` |
| POST `/runQuery` | `PostRunQuery.cpp` | `RunQueryHandler.cs` | `RunQuery.swift` | `RunQuery.java` | `tdk.ts` |
| POST `/snapshotDocuments` | `PostSnapshotDocuments.cpp` | `SnapshotDocumentsHandler.cs` | `SnapshotDocuments.swift` | `SnapshotDocs.java` | `snapshot.ts` |
| POST `/verifyDocuments` | `PostVerifyDocuments.cpp` | `VerifyDocumentsHandler.cs` | `VerifyDocuments.swift` | `VerifyDocs.java` | `snapshot.ts` |

## Deployment Registration

Each platform is registered for AWS deployment in [environment/aws/topology_setup/test_server_platforms/](../environment/aws/topology_setup/test_server_platforms/). All registered classes extend `TestServer` and implement `PlatformBridge` (`validate`, `install`, `run`, `stop`, `uninstall`, `get_ip`).

| File | Registered Platform Keys |
|---|---|
| `c_register.py` | `c_macos`, `c_linux_x86_64`, `c_windows`, `c_ios`, `c_android` |
| `dotnet_register.py` | `dotnet_macos`, `dotnet_windows`, `dotnet_ios`, `dotnet_android` |
| `swift_register.py` | `swift_ios` |
| `java_register.py` | `jak_android`, `jak_desktop`, `jak_webservice` |
| `js_register.py` | `js` |

## Rules

- **Implement every endpoint** in `spec/api/api.yaml`.
- **Handle API v1 and v2** — version is sent in `CBLTest-API-Version` header.
- **Return required response headers**: `CBLTest-API-Version`, `CBLTest-Server-ID`.
- **Return proper error codes** with descriptive messages on failure.
- **Adding a new endpoint** requires updates in: all 5 platforms + the OpenAPI spec + the Python framework.
- **New platform?** Follow existing patterns and add a `*_register.py` in `environment/aws/topology_setup/test_server_platforms/`.
- **Build scripts** must support release (`BLD_NUM=0`) and CI URLs.
- **Keep handler logic consistent** across platforms — same validation and error semantics.

## Commands

```bash
# C
cd servers/c && ./scripts/build_macos.sh 4.0.0 43 && cd build/out/bin && ./testserver
cd servers/c && ./scripts/build_linux.sh   4.0.0 43
cd servers/c && ./scripts/build_ios.sh     all 4.0.0 43
cd servers/c && ./scripts/build_android.sh all enterprise 4.0.0 43
cd servers/c && .\scripts\build_wins.ps1 -Edition enterprise -Version 4.0.0 -Build 43   # PowerShell

# .NET — built via the orchestrator (dotnet_register.py runs `dotnet publish`), no standalone build script

# iOS
cd servers/ios && ./Scripts/build.sh all enterprise 4.0.0 43

# JVM
cd servers/jak/desktop    && ./gradlew build
cd servers/jak/android    && ./gradlew build
cd servers/jak/webservice && ./gradlew build

# JavaScript
cd servers/javascript && npm install && npm run dev
```

## Cross-References

| What | Where | Relationship |
|---|---|---|
| API contract | [spec/api/api.yaml](../spec/api/api.yaml) | Defines what every server implements |
| Python framework | [client/src/cbltest/](../client/src/cbltest/) | Sends requests to these servers |
| Test suites | [tests/dev_e2e/](../tests/dev_e2e/), [tests/QE/](../tests/QE/) | Exercise these servers via the framework |
| Platform bridges | [environment/aws/topology_setup/test_server_platforms/](../environment/aws/topology_setup/test_server_platforms/) | Deploys and manages servers in AWS |
| CI prebuild | [jenkins/pipelines/prebuild/](../jenkins/pipelines/prebuild/) | Builds server artifacts for CI |
| CI test pipelines | [jenkins/pipelines/dev_e2e/](../jenkins/pipelines/dev_e2e/), [jenkins/pipelines/QE/](../jenkins/pipelines/QE/) | Runs tests against these servers |
