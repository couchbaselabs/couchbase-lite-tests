# Agent: cbltest Framework (client/)

## Identity

You are a specialized agent for the `cbltest` Python package — the core test framework
of the Couchbase Lite System Test Harness ("TDK"). You understand the request/response
versioning system, pytest plugin architecture, and async I/O patterns used throughout.

## Scope

You own all code under `client/`:
- `client/src/cbltest/` — Framework source code
- `client/smoke_tests/` — Smoke test suite
- `client/pyproject.toml` — Package config, dependencies, plugin entry points

You do NOT directly own the test suites (`tests/`), platform servers (`servers/`),
infrastructure (`environment/`), or CI pipelines (`jenkins/`), but you understand
how they interact with your code.

## Architecture

```
cbltest/
├── __init__.py         # CBLPyTest — top-level entry point
├── requests.py         # RequestFactory + TestServerRequestType enum + registries
├── responses.py        # Response registry
├── version.py          # __version__ = "2.0.3"; available_api_version() supports v1 & v2
│
├── api/                # High-level API classes (public interface for test authors)
│   ├── testserver.py   #   TestServer — per-platform server communication
│   ├── database.py     #   Database — CRUD, snapshot, verify, query
│   ├── replicator.py   #   Replicator — start/stop/status for sync
│   ├── listener.py     #   Listener — passive peer for P2P
│   ├── syncgateway.py  #   SyncGateway — SGW admin API wrapper
│   ├── couchbaseserver.py # CouchbaseServer — CBS bucket/scope/collection mgmt
│   ├── edgeserver.py   #   EdgeServer — edge server management
│   ├── cbltestclass.py #   CBLTestClass — base class for class-based tests
│   ├── multipeer_replicator.py # MultipeerReplicator
│   └── ...             #   error types, JSON helpers, x509, cloud
│
├── v1/                 # API v1: requests.py, responses.py
├── v2/                 # API v2: requests.py, responses.py
│
├── plugins/            # Pytest plugins (auto-loaded via entry points)
│   ├── cblpytest_fixture.py      # `cblpytest` session fixture
│   ├── required_topology.py      # min_test_servers, min_sync_gateways markers
│   ├── cbse_filter.py            # CBS edition filtering
│   ├── greenboard_fixture.py     # Test result upload
│   └── span_generation_fixture.py # OpenTelemetry spans
│
├── configparser.py     # Parses test config JSON
├── logging.py          # cbl_info, cbl_error, cbl_warning, LogLevel
└── httplog.py          # HTTP request/response logging
```

## Core Concepts

### CBLPyTest (the entry point)
Created via `await CBLPyTest.create(config_path)`. It:
1. Parses the JSON config → `ParsedConfig`
2. Creates a `RequestFactory` (HTTP transport layer)
3. Creates `TestServer[]`, `SyncGateway[]`, `CouchbaseServer[]`, `EdgeServer[]`
4. Resolves API version — queries all test servers, they must agree
5. Starts a session on each test server

Properties: `.request_factory`, `.test_servers`, `.sync_gateways`, `.couchbase_servers`,
`.edge_servers`, `.load_balancers`, `.config`, `.log_level`, `.extra_props`

### RequestFactory & Versioned Registry
```python
# Registration pattern (in v1/requests.py or v2/requests.py):
@register_request(TestServerRequestType.RESET, version=1)
class PostResetRequestV1(TestServerRequest):
    ...

@register_body(TestServerRequestType.RESET, version=1)
class PostResetRequestBodyV1(JSONSerializable):
    ...
```

The `RequestFactory` looks up the correct request class from `_request_registry[(type, version)]`
at runtime based on the negotiated API version.

### TestServerRequestType enum
All known operations:
`ROOT`, `RESET`, `ALL_DOC_IDS`, `UPDATE_DB`, `START_REPLICATOR`, `REPLICATOR_STATUS`,
`SNAPSHOT_DOCS`, `VERIFY_DOCS`, `PERFORM_MAINTENANCE`, `RUN_QUERY`, `GET_DOCUMENT`,
`NEW_SESSION`, `LOG`, `START_LISTENER`, `STOP_LISTENER`, `START_MULTIPEER_REPLICATOR`,
`STOP_MULTIPEER_REPLICATOR`, `MULTIPEER_REPLICATOR_STATUS`

### Pytest Plugins
Registered in `client/pyproject.toml`:
```toml
[project.entry-points.pytest11]
required_topology = "cbltest.plugins.required_topology"
cbse_filter = "cbltest.plugins.cbse_filter"
cblpytest_fixture = "cbltest.plugins.cblpytest_fixture"
greenboard_fixture = "cbltest.plugins.greenboard_fixture"
span_generation_fixture = "cbltest.plugins.span_generation_fixture"
```

CLI options added by `cblpytest_fixture`:
- `--config PATH` (required) — JSON config file
- `--cbl-log-level LEVEL` — error/warning/info/verbose/debug
- `--test-props PATH` — Extra test properties JSON
- `--otel-endpoint HOST` — OpenTelemetry collector
- `--dataset-version VERSION` — Dataset version (default: "4.0")

## How To Add Things

### New Request Type
1. Add entry to `TestServerRequestType` enum in `requests.py`
2. Create request class in `v1/requests.py` and/or `v2/requests.py`
3. Decorate: `@register_request(TestServerRequestType.NEW_TYPE, version=1)` (or `[1, 2]`)
4. If body needed: `@register_body(TestServerRequestType.NEW_TYPE, version=1)`
5. Create response in `v1/responses.py` and/or `v2/responses.py`

### New API Class (e.g., a new component wrapper)
1. Create `api/new_component.py`
2. Accept `RequestFactory` in constructor, use it to send typed requests
3. Expose via `CBLPyTest` properties in `__init__.py`

### New Pytest Plugin
1. Create `plugins/my_plugin.py`
2. Register in `client/pyproject.toml` under `[project.entry-points.pytest11]`
3. Implement hooks: `pytest_addoption`, `pytest_runtest_setup`, fixtures, etc.
4. ⚠️ Never break plugin signatures — they are auto-loaded by pytest

### New API Version (e.g., v3)
1. Create `v3/` directory with `__init__.py`, `requests.py`, `responses.py`
2. Update `available_api_version()` in `version.py` to accept version 3
3. Register new classes with `version=3`
4. v1 and v2 must continue working (backward compatibility required)

## Coding Rules

- **Python 3.10+**: always `X | Y`, never `Union[X, Y]` or `Optional[X]`
- **Async I/O**: all network calls use `aiohttp`; test fixtures use `pytest-asyncio`
- **Imports**: `ruff` import sorting (`I` rules); relative imports within `cbltest`
- **Type hints**: required on all public methods; `ty` for type checking
- **Formatting**: `ruff format`; linting: `ruff check`
- **No breaking changes** to plugin contracts or public API without versioning

## Commands
```bash
uv sync                              # Install deps (from repo root)
uv run ruff check client/            # Lint
uv run ruff format client/           # Format
uv run --group lint ty check         # Type check
cd client/smoke_tests && uv run pytest -x -v --config config_in.json  # Smoke tests
```

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| API contract | `spec/api/api.yaml` | Defines what test servers must implement |
| Test suites | `tests/dev_e2e/`, `tests/QE/` | Consumers of this framework |
| Test servers | `servers/{c,dotnet,ios,jak,javascript}/` | Implement the API this framework calls |
| Infrastructure | `environment/{aws,docker}/` | Deploys the test environment |
| CI/CD | `jenkins/pipelines/` | Runs tests using this framework |
| Config schema | `testserver.schema.json` (remote) | Validates config files this framework parses |

