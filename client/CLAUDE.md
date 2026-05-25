# CLAUDE.md — cbltest Framework (client/)

## What This Is

The `cbltest` package is the Python test framework for the Couchbase Lite System Test Harness.
It is an HTTP request factory with telemetry and logging, packaged as a pytest plugin suite.
Tests send REST API calls to per-platform test servers, which execute Couchbase Lite operations.

## Package Structure

```
client/
├── pyproject.toml              # Hatchling build config, dependencies, pytest plugin entry points
├── smoke_tests/                # Minimal smoke tests for basic framework functionality
│   ├── conftest.py             # dataset_path fixture (relative: ../dataset/sg)
│   └── test_*.py               # Individual smoke tests
└── src/cbltest/
    ├── __init__.py             # CBLPyTest class — top-level entry point (create, close, resolve_api_version)
    ├── version.py              # __version__ = "2.0.2", available_api_version() — supports v1 and v2
    ├── globals.py              # CBLPyTestGlobal — shared state (running_test_name, auto_start_tdk_page)
    │
    ├── requests.py             # RequestFactory, TestServerRequestType enum, @register_request / @register_body decorators
    ├── request_types.py        # Base request type classes (GetRootRequest, TestServerRequest, etc.)
    ├── requests_transport.py   # HTTP transport layer for requests
    ├── responses.py            # TestServerResponse, response registry
    ├── response_types.py       # Response type definitions
    │
    ├── configparser.py         # _parse_config(), ParsedConfig, TestServerInfo, SyncGatewayInfo, CouchbaseServerInfo, EdgeServerInfo
    ├── extrapropsparser.py     # _parse_extra_props() for test properties JSON
    ├── jsonhelper.py           # JSON parsing utilities (_assert_string_entry, _get_typed, etc.)
    ├── assertions.py           # _assert_not_null and similar assertion helpers
    │
    ├── logging.py              # cbl_info, cbl_error, cbl_warning, cbl_log_init, LogLevel enum
    ├── httplog.py              # HTTP request/response logging (get_next_writer)
    ├── greenboarduploader.py   # Upload test results to Greenboard
    ├── utils.py                # General utilities
    ├── websocket_router.py     # WebSocket routing support
    │
    ├── api/                    # High-level API classes (the main public interface)
    │   ├── cbltestclass.py     # CBLTestClass — base class for class-based tests (mark_test_step, skip_if_*)
    │   ├── testserver.py       # TestServer — communicates with platform test servers
    │   ├── database.py         # Database — CRUD, snapshot, verify, query operations
    │   ├── database_types.py   # Database type definitions
    │   ├── replicator.py       # Replicator — start/stop/status for sync operations
    │   ├── replicator_types.py # Replicator configuration types
    │   ├── listener.py         # Listener — passive peer for P2P replication
    │   ├── multipeer_replicator.py      # MultipeerReplicator — multi-peer sync
    │   ├── multipeer_replicator_types.py # MultipeerReplicator types
    │   ├── syncgateway.py      # SyncGateway — admin API wrapper (create/delete DBs, users, etc.)
    │   ├── couchbaseserver.py  # CouchbaseServer — bucket/scope/collection management via SDK
    │   ├── edgeserver.py       # EdgeServer — edge server management
    │   ├── cloud.py            # Cloud/Capella integration
    │   ├── error.py            # CblTestServerBadResponseError and related exceptions
    │   ├── error_types.py      # Error type definitions
    │   ├── json_generator.py   # Test document generation
    │   ├── jsonserializable.py # JSONSerializable base class
    │   ├── test_functions.py   # Shared test helper functions
    │   └── x509_certificate.py # X.509 certificate handling for TLS tests
    │
    ├── v1/                     # API version 1 implementations
    │   ├── requests.py         # v1 request classes (registered with @register_request(..., version=1))
    │   └── responses.py        # v1 response classes
    │
    ├── v2/                     # API version 2 implementations
    │   ├── requests.py         # v2 request classes (registered with @register_request(..., version=2))
    │   └── responses.py        # v2 response classes
    │
    └── plugins/                # Pytest plugins (registered in pyproject.toml entry-points)
        ├── cblpytest_fixture.py      # `cblpytest` session-scoped fixture (creates CBLPyTest instance)
        ├── required_topology.py      # Topology markers: min_test_servers, min_sync_gateways, etc.
        ├── cbse_filter.py            # CBSE (Couchbase Server Edition) test filtering
        ├── greenboard_fixture.py     # Greenboard test result upload fixture
        └── span_generation_fixture.py # OpenTelemetry span generation for test tracing
```

## Key Classes and Entry Points

### `CBLPyTest` (in `__init__.py`)
The top-level orchestrator. Created via `CBLPyTest.create(config_path, ...)`:
- Parses config JSON → creates `RequestFactory`, `TestServer[]`, `SyncGateway[]`, `CouchbaseServer[]`, `EdgeServer[]`
- Resolves API version from test servers (must all agree)
- Provides `.request_factory`, `.test_servers`, `.sync_gateways`, `.couchbase_servers`, `.edge_servers`

### `RequestFactory` (in `requests.py`)
Central request dispatch. Routes requests based on `TestServerRequestType` + API version.
- Registry: `_request_registry[(type, version)] -> class`
- Registry: `_body_registry[(type, version)] -> class`

### `TestServerRequestType` enum (in `requests.py`)
All supported operations: `ROOT`, `RESET`, `ALL_DOC_IDS`, `UPDATE_DB`, `START_REPLICATOR`,
`REPLICATOR_STATUS`, `SNAPSHOT_DOCS`, `VERIFY_DOCS`, `PERFORM_MAINTENANCE`, `RUN_QUERY`,
`GET_DOCUMENT`, `NEW_SESSION`, `LOG`, `START_LISTENER`, `STOP_LISTENER`,
`START_MULTIPEER_REPLICATOR`, `STOP_MULTIPEER_REPLICATOR`, `MULTIPEER_REPLICATOR_STATUS`

### Pytest Plugin Registration (in `pyproject.toml`)
```toml
[project.entry-points.pytest11]
required_topology = "cbltest.plugins.required_topology"
cbse_filter = "cbltest.plugins.cbse_filter"
cblpytest_fixture = "cbltest.plugins.cblpytest_fixture"
greenboard_fixture = "cbltest.plugins.greenboard_fixture"
span_generation_fixture = "cbltest.plugins.span_generation_fixture"
```

### CLI Options Added by Plugins
- `--config PATH` (required) — JSON config file for the test environment
- `--cbl-log-level LEVEL` — Log level: error, warning, info, verbose, debug (default: warning)
- `--test-props PATH` — Extra test properties JSON file
- `--otel-endpoint HOST` — OpenTelemetry collector host for tracing
- `--dataset-version VERSION` — Dataset version for test servers (default: "4.0")

## How To Add Things

### Adding a New Request Type
1. Add entry to `TestServerRequestType` enum in `requests.py`
2. Create request class in `v1/requests.py` and/or `v2/requests.py`
3. Decorate with `@register_request(TestServerRequestType.NEW_TYPE, version=1)` (or `[1, 2]` for both)
4. Create body class if needed, decorate with `@register_body(...)`
5. Create corresponding response class in `v1/responses.py` and/or `v2/responses.py`

### Adding a New API Class
1. Create class in `api/` directory (e.g., `api/new_component.py`)
2. The class should use `RequestFactory` to send requests
3. Expose it via `CBLPyTest` properties in `__init__.py`

### Adding a New Pytest Plugin
1. Create module in `plugins/` (e.g., `plugins/my_plugin.py`)
2. Register in `pyproject.toml` under `[project.entry-points.pytest11]`
3. Define hooks (`pytest_addoption`, `pytest_runtest_setup`, fixtures, etc.)

### Adding a New API Version (e.g., v3)
1. Create `v3/` directory with `__init__.py`, `requests.py`, `responses.py`
2. Update `available_api_version()` in `version.py` to accept version 3
3. Register new request/response classes with `version=3`

## Build & Development Commands
```bash
# Install (from repo root)
uv sync

# Run smoke tests
cd client/smoke_tests && uv run pytest -x -v --config config_in.json

# Type check
uv run --group lint ty check

# Lint & format
uv run ruff check client/
uv run ruff format client/
```

## Rules
- **Python 3.10+**: use `X | Y` not `Union[X, Y]`; use `X | None` not `Optional[X]`
- **All I/O is async**: use `aiohttp`, `pytest-asyncio`, `async def`
- **Never break plugin contracts**: plugins are auto-loaded by pytest; changing signatures breaks all tests
- **Version compatibility**: v1 and v2 must both continue working; version negotiation happens at session start
- **Imports**: use `ruff` import sorting (`I` rules); relative imports within `cbltest` package

## Cross-References
- API contract: `spec/api/api.yaml` (OpenAPI spec)
- Test suites that consume this: `tests/dev_e2e/`, `tests/QE/`
- Test server implementations: `servers/{c,dotnet,ios,jak,javascript}/`
- Infrastructure that deploys the environment: `environment/{aws,docker}/`

