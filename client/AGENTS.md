# cbltest Framework — `client/`

The `cbltest` Python package is the test framework that drives platform test servers via HTTP. It is an async request factory + pytest plugin suite. Tests in `tests/dev_e2e/` and `tests/QE/` consume this package; per-platform servers in `servers/` implement the API it calls.

## Scope

You own everything under `client/`:
- `client/src/cbltest/` — framework source
- `client/smoke_tests/` — smoke tests for the framework itself
- `client/pyproject.toml` — hatchling build config + pytest plugin entry points

You do **not** own `tests/`, `servers/`, `environment/`, or `jenkins/`, but you understand how they consume this package.

## Package Layout

```
client/
├── pyproject.toml                # hatchling build, deps, pytest plugin entry points
├── smoke_tests/                  # minimal smoke tests + ../dataset/sg fixture
└── src/cbltest/
    ├── __init__.py               # CBLPyTest — top-level entry (create/close/resolve_api_version)
    ├── version.py                # __version__ = "2.0.3"; available_api_version() — v1, v2
    ├── globals.py                # CBLPyTestGlobal — shared state
    │
    ├── requests.py               # RequestFactory, TestServerRequestType, @register_request / @register_body
    ├── request_types.py          # Base request type classes
    ├── requests_transport.py     # HTTP transport
    ├── responses.py              # TestServerResponse + response registry
    ├── response_types.py         # Response type definitions
    │
    ├── configparser.py           # _parse_config(), ParsedConfig, {TestServer,SyncGateway,CouchbaseServer,EdgeServer}Info
    ├── extrapropsparser.py       # _parse_extra_props()
    ├── jsonhelper.py             # JSON helpers (_assert_string_entry, _get_typed, …)
    ├── assertions.py             # _assert_not_null and friends
    │
    ├── logging.py                # cbl_info / cbl_error / cbl_warning / cbl_log_init, LogLevel
    ├── httplog.py                # HTTP request/response logging (get_next_writer)
    ├── greenboarduploader.py     # Upload test results to Greenboard
    ├── websocket_router.py       # WebSocket routing (used by JS server)
    ├── utils.py                  # General utilities
    │
    ├── api/                      # Public interface for test authors
    │   ├── cbltestclass.py       # CBLTestClass — base class; mark_test_step(), skip_if_*()
    │   ├── testserver.py         # TestServer — communicates with platform servers
    │   ├── database.py           # Database — CRUD, snapshot, verify, query
    │   ├── database_types.py
    │   ├── replicator.py         # Replicator — start/stop/status
    │   ├── replicator_types.py
    │   ├── listener.py           # Listener — passive P2P peer
    │   ├── multipeer_replicator.py
    │   ├── multipeer_replicator_types.py
    │   ├── syncgateway.py        # SyncGateway admin API
    │   ├── couchbaseserver.py    # CBS bucket/scope/collection mgmt (via SDK)
    │   ├── edgeserver.py
    │   ├── cloud.py              # Cloud / Capella integration
    │   ├── error.py              # CblTestServerBadResponseError etc.
    │   ├── error_types.py
    │   ├── json_generator.py     # Test document generation
    │   ├── jsonserializable.py
    │   ├── test_functions.py     # Shared test helpers
    │   └── x509_certificate.py   # TLS cert handling
    │
    ├── v1/                       # API v1 implementations
    │   ├── requests.py           #   @register_request(..., version=1)
    │   └── responses.py
    │
    ├── v2/                       # API v2 implementations
    │   ├── requests.py           #   @register_request(..., version=2)
    │   └── responses.py
    │
    └── plugins/                  # Pytest plugins (auto-loaded via entry points)
        ├── cblpytest_fixture.py        # session-scoped `cblpytest` fixture
        ├── required_topology.py        # min_test_servers / min_sync_gateways / … markers
        ├── cbse_filter.py              # CBSE (CBS Edition) test filtering
        ├── greenboard_fixture.py
        └── span_generation_fixture.py  # OpenTelemetry spans
```

## Core Concepts

### `CBLPyTest` — the entry point

```python
cblpytest = await CBLPyTest.create(parsed_config, ...)
```

Takes an already-parsed `ParsedConfig` (the `cblpytest` pytest fixture parses the `--config` JSON once in `pytest_configure` and stashes it on `pytest.Config`; see `plugins/cblpytest_fixture.py`). It:
1. Creates a `RequestFactory` (HTTP transport)
2. Creates `TestServer[]`, `SyncGateway[]`, `CouchbaseServer[]`, `EdgeServer[]`, `LoadBalancer[]`
3. Resolves the API version — queries every test server, requires consensus
4. Starts a session on each test server

Exposed properties: `.request_factory`, `.test_servers`, `.sync_gateways`, `.couchbase_servers`, `.edge_servers`, `.load_balancers`, `.config`, `.log_level`, `.extra_props`.

### `RequestFactory` + versioned registry

Two registries indexed by `(TestServerRequestType, version)` resolve request/body classes at call time. Register with decorators:

```python
@register_request(TestServerRequestType.RESET, version=1)
class PostResetRequestV1(TestServerRequest): ...


@register_body(TestServerRequestType.RESET, version=1)
class PostResetRequestBodyV1(JSONSerializable): ...
```

### `TestServerRequestType` enum (in `requests.py`)

18 values — keep in sync with the file:
`ROOT`, `RESET`, `ALL_DOC_IDS`, `UPDATE_DB`, `START_REPLICATOR`, `REPLICATOR_STATUS`, `SNAPSHOT_DOCS`, `VERIFY_DOCS`, `PERFORM_MAINTENANCE`, `RUN_QUERY`, `GET_DOCUMENT`, `NEW_SESSION`, `LOG`, `START_LISTENER`, `STOP_LISTENER`, `START_MULTIPEER_REPLICATOR`, `STOP_MULTIPEER_REPLICATOR`, `MULTIPEER_REPLICATOR_STATUS`.

(Note: `/stopReplicator` exists in the OpenAPI spec but the framework drives it through `Replicator.stop()` state transitions rather than a dedicated enum value.)

### Pytest plugins + CLI options

Registered in `client/pyproject.toml`:

```toml
[project.entry-points.pytest11]
required_topology       = "cbltest.plugins.required_topology"
cbse_filter             = "cbltest.plugins.cbse_filter"
cblpytest_fixture       = "cbltest.plugins.cblpytest_fixture"
greenboard_fixture      = "cbltest.plugins.greenboard_fixture"
span_generation_fixture = "cbltest.plugins.span_generation_fixture"
```

CLI options added by `cblpytest_fixture`:

| Option | Purpose |
|---|---|
| `--config PATH` *(required)* | JSON config file |
| `--cbl-log-level LEVEL` | `error` / `warning` / `info` / `verbose` / `debug` (default `warning`) |
| `--test-props PATH` | Extra test properties JSON |
| `--otel-endpoint HOST` | OpenTelemetry collector |
| `--dataset-version VERSION` | Default `"4.0"` |

## How To Add Things

| Goal | Steps |
|---|---|
| **New request type** | 1. Add to `TestServerRequestType` in `requests.py`<br>2. Implement in `v1/requests.py` and/or `v2/requests.py` with `@register_request(..., version=N)`<br>3. If a body is needed, `@register_body(..., version=N)`<br>4. Implement response in `v{1,2}/responses.py` |
| **New API class** | 1. Add `api/new_component.py`<br>2. Accept `RequestFactory` in constructor; use it for typed requests<br>3. Expose via `CBLPyTest` properties in `__init__.py` |
| **New pytest plugin** | 1. Add `plugins/my_plugin.py`<br>2. Register in `client/pyproject.toml` under `[project.entry-points.pytest11]`<br>3. Implement hooks (`pytest_addoption`, fixtures, …)<br>4. **Do not break existing plugin signatures** — they are auto-loaded by pytest |
| **New API version** (e.g. v3) | 1. Create `v3/` with `__init__.py`, `requests.py`, `responses.py`<br>2. Extend `available_api_version()` in `version.py`<br>3. Register classes with `version=3`<br>4. v1 and v2 must keep working — backward compatibility is required |

## Rules

- **Python 3.10+** — `X | Y`, never `Union[X, Y]` / `Optional[X]`.
- **Async everywhere** — `aiohttp`, `pytest-asyncio`, `async def`.
- **Type hints on every public method** — checked by `ty`.
- **Imports**: `ruff` import sort (`I` rules); relative imports inside `cbltest`.
- **No breaking changes** to plugin contracts or public API classes without a version bump.
- v1 and v2 must coexist; version negotiation happens once per session.

## Commands

```bash
uv sync                                          # install (from repo root)
uv run ruff check client/                        # lint
uv run ruff format client/                       # format
uv run --group lint ty check                     # type check
cd client/smoke_tests && uv run pytest -x -v --config config_in.json
```

## Cross-References

| What | Where | Relationship |
|---|---|---|
| API contract | [spec/api/api.yaml](../spec/api/api.yaml) | Defines what test servers implement |
| Test suites | [tests/dev_e2e/](../tests/dev_e2e/), [tests/QE/](../tests/QE/) | Consume this framework |
| Platform servers | [servers/](../servers/) (c, dotnet, ios, jak, javascript) | Implement the API this calls |
| Infrastructure | [environment/](../environment/) (aws, docker) | Deploys the test environment |
| CI | [jenkins/pipelines/](../jenkins/pipelines/) | Drives tests using this framework |
| Config schema | `https://packages.couchbase.com/couchbase-lite/testserver.schema.json` | Validates config files |
