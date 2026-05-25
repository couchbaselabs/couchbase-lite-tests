# CLAUDE.md — Platform Test Servers (servers/)

## What This Is

This directory contains the per-platform test server implementations for the Couchbase Lite
System Test Harness. Each server implements the same REST API (defined in `spec/api/api.yaml`)
in the native language for its platform, allowing the Python test framework to drive Couchbase
Lite operations uniformly across C, .NET, Swift, Kotlin/Java, and JavaScript.

## Platforms

| Directory | Language | Build System | Target Platforms | API Transport |
|-----------|----------|-------------|------------------|---------------|
| `c/` | C++ (C++17) | CMake 3.23+ | macOS, Linux, Windows, iOS, Android | HTTP (CivetWeb) |
| `dotnet/` | C# (.NET 8) | MSBuild/dotnet CLI | Windows, macOS, Linux | HTTP (Kestrel) |
| `ios/` | Swift | Xcode | iOS (device + simulator) | HTTP |
| `jak/` | Java/Kotlin | Gradle | Android, JVM Desktop, Web Service | HTTP |
| `javascript/` | TypeScript | Vite/Vitest | Browser (via WebSocket) | WebSocket |

## Common Architecture (All Platforms)

Every server implements the **same logical architecture**:

```
┌─────────────────────┐
│   HTTP/WS Listener  │  ← Receives requests from Python test framework
├─────────────────────┤
│     Router/         │  ← Maps URI paths to handler functions
│     Dispatcher      │
├─────────────────────┤
│     Handlers        │  ← One handler per API endpoint (see below)
├─────────────────────┤
│   CBL Wrapper/      │  ← Platform-specific Couchbase Lite SDK calls
│   Manager           │
├─────────────────────┤
│   Session Manager   │  ← Manages test sessions (databases, replicators)
└─────────────────────┘
```

### API Endpoints (from `spec/api/api.yaml`)

Every server must implement these endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Root info: API version, server UUID, CBL version, platform |
| `/newSession` | POST | Create a new test session |
| `/reset` | POST | Reset databases (create, load dataset, or delete) |
| `/getAllDocuments` | POST | Get all document IDs in specified collections |
| `/updateDatabase` | POST | CRUD operations on documents |
| `/startReplicator` | POST | Start a replication session |
| `/getReplicatorStatus` | POST | Get replicator status/activity |
| `/snapshotDocuments` | POST | Snapshot document state for later verification |
| `/verifyDocuments` | POST | Verify documents match a previous snapshot |
| `/performMaintenance` | POST | Compact, integrity check, etc. |
| `/runQuery` | POST | Execute N1QL queries |
| `/getDocument` | POST | Get a specific document by ID |
| `/log` | POST | Write to server-side log |
| `/startListener` | POST | Start a P2P passive listener |
| `/stopListener` | POST | Stop a P2P passive listener |
| `/startMultipeerReplicator` | POST | Start multipeer mesh replication |
| `/stopMultipeerReplicator` | POST | Stop multipeer mesh replication |
| `/getMultipeerReplicatorStatus` | POST | Get multipeer replicator status |

## Per-Platform Details

### C Server (`c/`)
```
c/
├── CMakeLists.txt          # Top-level CMake config
├── scripts/                # Build scripts per OS
│   ├── download_cbl.sh     # Downloads CBL C SDK (platform-specific URLs)
│   ├── build_macos.sh      # download → cmake → make → copy dylibs + assets
│   ├── build_linux.sh      # Same flow for Linux
│   ├── build_ios.sh        # Same flow for iOS
│   ├── build_android.sh    # Same flow for Android
│   └── build_wins.ps1      # Same flow for Windows (PowerShell)
├── src/
│   ├── TestServer.h/.cpp   # Main server class (CivetWeb-based)
│   ├── Dispatcher.h/.cpp   # Route dispatcher
│   ├── dispatcher/         # One .cpp per API endpoint (GetRoot.cpp, PostReset.cpp, ...)
│   ├── cbl/               # CBL wrapper classes (CBLManager, Snapshot, Fleece, etc.)
│   ├── Session.h           # Session management
│   └── main.cpp            # Entry point
├── vendor/                 # Third-party libs (CivetWeb, nlohmann/json)
├── lib/                    # Downloaded CBL SDK placed here by download_cbl.sh
└── platforms/              # Platform-specific build configs (iOS, Android)
```

Build: `./scripts/build_macos.sh <version> <build_num>` → artifacts in `build/out/bin/`

### .NET Server (`dotnet/`)
```
dotnet/
├── testserver.sln          # Visual Studio solution
├── testserver/             # ASP.NET web host project
├── testserver.cli/         # CLI entry point project
├── testserver.logic/       # Core logic (handlers, router, services)
│   ├── Handlers/           # One .cs per endpoint (GetRootHandler.cs, ResetDatabaseHandler.cs, ...)
│   ├── Services/           # Business logic services
│   ├── Router.cs           # Request routing
│   └── TestServer.cs       # Server lifecycle
└── scripts/                # build_cli.sh, run_cli.sh, etc.
```

Build: `./scripts/build_cli.sh` → `dotnet publish`

### iOS Server (`ios/`)
```
ios/
├── TestServer.xcodeproj/   # Xcode project
├── TestServer/
│   ├── Handlers/           # One .swift per endpoint (GetRootHandler.swift, ResetHandler.swift, ...)
│   ├── Server/             # HTTP server implementation
│   ├── Middleware/         # Request processing middleware
│   ├── ContentTypes/       # Request/response content types
│   └── Utils/              # Utilities
├── Scripts/                # build.sh, download_cbl.sh, gen_cbl_version.sh
└── Frameworks/             # Downloaded CouchbaseLiteSwift.xcframework
```

Build: `./Scripts/build.sh <type> <edition> <version> <build_num>` → `.app` in `build/`

### JVM/Kotlin Server (`jak/`)
```
jak/
├── version.txt             # Server version (e.g., "1.2.1")
├── shared/                 # Shared code across all JVM variants
│   ├── common/             # Platform-agnostic logic
│   │   └── main/java/.../endpoints/v1/  # Handler classes (GetAllDocs, UpdateDb, RunQuery, etc.)
│   ├── jvm/                # JVM-specific code (BaseTestApp, PlatformDispatcher)
│   └── server/             # HTTP server implementation
├── android/                # Android app variant (Gradle)
├── desktop/                # Desktop JVM variant (Gradle)
└── webservice/             # Web service variant (Gradle)
```

Build: `cd <variant> && ./gradlew build`

### JavaScript Server (`javascript/`)
```
javascript/
├── package.json            # npm config (@couchbase/test-server)
├── tsconfig.json           # TypeScript config (ES2022, strict)
├── vite.config.js          # Vite bundler config
├── eslint.config.mjs       # ESLint config
└── src/
    ├── testServer.ts       # Main server (WebSocket-based, not HTTP)
    ├── tdk.ts              # TDK integration
    ├── tdkSchema.ts        # Schema definitions
    ├── snapshot.ts          # Document snapshot logic
    ├── filters.ts           # Replication filters
    ├── conflictResolvers.ts # Conflict resolution
    ├── keyPath.ts           # KeyPath implementation
    ├── utils.ts             # Utilities
    └── webSocketClient.ts   # WebSocket client for TDK communication
```

Build: `npm install && npm run dev`

**Note:** The JS server uses **WebSocket** instead of HTTP. The Python framework handles
this via `websocket_router.py` in `client/src/cbltest/`.

## Build Script Patterns (Repetitive)

All platform build scripts follow the same logical flow:
1. **Download CBL library** — `download_cbl.sh` fetches platform-specific CBL SDK from `latestbuilds` or `packages.couchbase.com`
2. **Build** — Platform-specific compiler (cmake, dotnet, xcodebuild, gradle)
3. **Copy assets** — Dataset files, config, dynamic libraries
4. **Package** — Output in `build/` or `out/` directory

URL patterns:
- Release builds: `https://packages.couchbase.com/releases/couchbase-lite-{platform}/{version}/...`
- CI builds: `http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-lite-{platform}/{version}/{build_num}/...`

## Deployment Registration

Each platform is registered in `environment/aws/topology_setup/test_server_platforms/`:
- `c_register.py` — C platform variants (macOS, Linux, Windows, iOS, Android)
- `dotnet_register.py` — .NET platform variants
- `swift_register.py` — iOS/Swift platform
- `java_register.py` — JVM/Kotlin platform variants
- `js_register.py` — JavaScript platform

All extend `TestServer` base class and implement `PlatformBridge` for install/run/stop.

## Handler Pattern (Cross-Platform)

Each endpoint handler across all platforms follows the same pattern — here shown side by side:

| Endpoint | C (`dispatcher/`) | .NET (`Handlers/`) | Swift (`Handlers/`) | JVM (`endpoints/v1/`) |
|----------|-------------------|--------------------|--------------------|----------------------|
| GET `/` | `GetRoot.cpp` | `GetRootHandler.cs` | `GetRootHandler.swift` | (in `TestApp.java`) |
| POST `/reset` | `PostReset.cpp` | `ResetDatabaseHandler.cs` | `ResetHandler.swift` | (in `Session.java`) |
| POST `/startReplicator` | `PostStartReplicator.cpp` | `StartReplicatorHandler.cs` | `StartReplicator.swift` | `ReplicatorManager.java` |
| POST `/runQuery` | `PostRunQuery.cpp` | `RunQueryHandler.cs` | `RunQuery.swift` | `RunQuery.java` |
| ... | ... | ... | ... | ... |

When adding a new endpoint, **all five platforms must be updated**.

## Rules

- **Must implement ALL endpoints** defined in `spec/api/api.yaml`
- **Must handle API version 1 and 2** requests (version sent in `CBLTest-API-Version` header)
- **Must return proper response headers**: `CBLTest-API-Version`, `CBLTest-Server-ID`
- **Must return proper error codes** and messages on failure
- **When adding a new endpoint**: update all 5 platforms + the OpenAPI spec
- **New platform?** Follow existing patterns and register in `environment/aws/topology_setup/test_server_platforms/`
- **Build scripts** must support both release and CI build URLs

## Commands
```bash
# C server (macOS)
cd servers/c && ./scripts/build_macos.sh 4.0.0 43 && cd build/out/bin && ./testserver

# .NET server
cd servers/dotnet && ./scripts/build_cli.sh && ./scripts/run_cli.sh

# iOS server
cd servers/ios && ./Scripts/build.sh all enterprise 4.0.0 43

# JVM Desktop
cd servers/jak/desktop && ./gradlew build

# JavaScript
cd servers/javascript && npm install && npm run dev
```

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| API contract | `spec/api/api.yaml` | **Defines** what every server must implement |
| Python framework | `client/src/cbltest/` | Sends requests to these servers |
| Test suites | `tests/dev_e2e/`, `tests/QE/` | Exercise these servers indirectly |
| Platform bridges | `environment/aws/topology_setup/test_server_platforms/` | Deploy and manage these servers |
| CI prebuild | `jenkins/pipelines/prebuild/` | Builds server artifacts for CI |
| CI pipelines | `jenkins/pipelines/{dev_e2e,QE}/{platform}/` | Run tests against these servers |

