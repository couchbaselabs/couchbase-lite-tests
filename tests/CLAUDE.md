# CLAUDE.md — Test Suites (tests/)

## What This Is

This directory contains the two Python test suites that exercise Couchbase Lite via the
`cbltest` framework. Tests send REST API calls to per-platform test servers, which execute
Couchbase Lite operations against Sync Gateway and Couchbase Server.

## Directory Structure

```
tests/
├── dev_e2e/                  # Developer E2E tests — core replication & feature coverage
│   ├── conftest.py           # dataset_path fixture (../../dataset/sg)
│   ├── config.json           # Generated test config (DO NOT hand-edit)
│   ├── config.example.json   # Example config for reference
│   ├── test_basic_replication.py
│   ├── test_replication_filter.py
│   ├── test_replication_filter_data.py   # Helper data for filter tests
│   ├── test_replication_auto_purge.py
│   ├── test_replication_blob.py
│   ├── test_replication_behavior.py
│   ├── test_replication_upgrade.py
│   ├── test_replication_xdcr.py
│   ├── test_custom_conflict.py
│   ├── test_encrypted_properties.py
│   ├── test_fest.py
│   ├── test_multipeer.py
│   └── test_query_consistency.py
│
├── QE/                       # QA tests — broader coverage, edge cases, system tests
│   ├── conftest.py           # dataset_path + cleanup_after_test (auto SGW/CBS cleanup)
│   ├── config.json           # Generated test config (DO NOT hand-edit)
│   ├── test_db_online_offline.py
│   ├── test_delta_sync.py
│   ├── test_high_availability.py
│   ├── test_large_doc_workloads.py
│   ├── test_log_redaction.py
│   ├── test_multipeer.py
│   ├── test_multiple_servers.py
│   ├── test_no_conflicts.py
│   ├── test_peer_to_peer.py
│   ├── test_peer_to_peer_topology.py
│   ├── test_replication_eventing.py
│   ├── test_replication_functional.py
│   ├── test_replication_multiple_clients.py
│   ├── test_replicator_encryption_hook.py
│   ├── test_rolling_upgrade_sgw.py
│   ├── test_server_setup.py
│   ├── test_system_multipeer.py
│   ├── test_ttl.py
│   ├── test_upg_sgw.py
│   ├── test_users_channels.py
│   ├── test_xattrs.py
│   └── edge_server/           # Edge Server test sub-suite
│       ├── test_authentication.py
│       ├── test_blobs.py
│       ├── test_changes_feed.py
│       ├── test_chaos_scenarios.py
│       ├── test_crud.py
│       ├── test_database_edge_server.py
│       ├── test_logging.py
│       ├── test_query_edge_server.py
│       ├── test_replication_edge_server.py
│       ├── test_replication_sanity.py
│       ├── test_system.py
│       └── test_ttl_expires.py
│
└── .tools/
    └── cbbackupmgr/            # Couchbase Backup Manager binary for backup/restore tests
```

## Test Anatomy

Every test follows this pattern:

```python
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.replicator import Replicator, ReplicatorCollectionEntry, ReplicatorType
from cbltest.api.replicator_types import ReplicatorActivityLevel, ReplicatorBasicAuthenticator

@pytest.mark.min_test_servers(1)       # Topology requirement
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestFeatureName(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_something(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        # 1. Setup: configure SGW + CBS via CouchbaseCloud
        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "names")

        # 2. Reset local DB on test server
        self.mark_test_step("Reset local database, and load `names` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="names")
        db = dbs[0]

        # 3. Create and run replicator
        self.mark_test_step("Start a replicator...")
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("names"), ...)
        await replicator.start()

        # 4. Wait and assert
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None

        # 5. Cleanup
        await cblpytest.test_servers[0].cleanup()
```

## Key Fixtures

### `cblpytest` (session-scoped, auto-injected)
Provides access to the full test environment:
- `cblpytest.test_servers` — list of `TestServer` instances
- `cblpytest.sync_gateways` — list of `SyncGateway` instances
- `cblpytest.couchbase_servers` — list of `CouchbaseServer` instances
- `cblpytest.edge_servers` — list of `EdgeServer` instances
- `cblpytest.request_factory` — the `RequestFactory`

### `dataset_path` (session-scoped, per-suite conftest.py)
Returns `Path` to `dataset/sg/` directory. Defined in each suite's `conftest.py`:
- `tests/dev_e2e/conftest.py` → `Path(script_path, "..", "..", "dataset", "sg")`
- `tests/QE/conftest.py` → same path, plus the `cleanup_after_test` fixture

### `cleanup_after_test` (QE only, function-scoped, autouse)
Automatically cleans up SGW databases and CBS buckets after every `@pytest.mark.sgw` test.
Skips non-SGW tests. This is why QE tests don't need manual cleanup.

## Test Markers

| Marker | Meaning |
|--------|---------|
| `@pytest.mark.sgw` | Test focuses on Sync Gateway functionality |
| `@pytest.mark.cbl` | Test focuses on Couchbase Lite functionality |
| `@pytest.mark.upg_sgw` | Test focuses on SGW upgrade scenarios |
| `@pytest.mark.min_test_servers(N)` | Requires at least N test servers |
| `@pytest.mark.min_sync_gateways(N)` | Requires at least N Sync Gateways |
| `@pytest.mark.min_couchbase_servers(N)` | Requires at least N Couchbase Servers |
| `@pytest.mark.min_load_balancers(N)` | Requires at least N load balancers |
| `@pytest.mark.asyncio(loop_scope="session")` | Required on every async test |

## dev_e2e vs QE Differences

| Aspect | dev_e2e | QE |
|--------|---------|-----|
| Audience | Developers during CBL release | QA team, regression |
| Cleanup | Manual (`await ts.cleanup()`) | Auto (`cleanup_after_test` fixture) |
| Markers | Topology markers only | `@pytest.mark.sgw` / `.cbl` + topology |
| Edge Server | No | Yes (`edge_server/` subdirectory) |
| SGW Upgrade | `test_replication_upgrade.py` | `test_upg_sgw.py` |
| Multi-SGW | `test_replication_xdcr.py` (2 SGW + 2 CBS + LB) | `test_users_channels.py` (3+ SGW), `test_high_availability.py` |
| Spec docs | `spec/tests/dev_e2e/NNN-feature.md` | `spec/tests/QE/test_feature.md` |

## Corresponding Spec Documents
- Always check the spec before writing or modifying a test
- dev_e2e: `spec/tests/dev_e2e/001-basic-replication.md` through `012-replication-xdcr.md`
- QE: `spec/tests/QE/test_<feature>.md`

## Common cbltest API Classes Used in Tests

| Class | Import | Purpose |
|-------|--------|---------|
| `CBLTestClass` | `cbltest.api.cbltestclass` | Base class with `mark_test_step()`, `skip_if_*()` |
| `CouchbaseCloud` | `cbltest.api.cloud` | Wraps SGW + CBS for dataset setup |
| `Replicator` | `cbltest.api.replicator` | Start/stop/wait replication |
| `Database` | `cbltest.api.database` | CRUD, snapshot, verify, query |
| `Listener` | `cbltest.api.listener` | P2P passive listener |
| `MultipeerReplicator` | `cbltest.api.multipeer_replicator` | Multi-device mesh sync |
| `SyncGateway` | `cbltest.api.syncgateway` | SGW admin API (users, roles, docs, DBs) |
| `CouchbaseServer` | `cbltest.api.couchbaseserver` | CBS bucket/scope management |
| `SnapshotUpdater` | `cbltest.api.database` | Batch document updates via `async with db.batch_updater()` |

## Datasets
Available datasets (in `dataset/sg/`): `names`, `travel`, `posts`, `todo`, `short_expiry`, `upgrade`
Each has a `-sg.json` (data) and `-sg-config.json` (SGW config) file.

## Commands
```bash
# Run all dev_e2e tests
cd tests/dev_e2e && uv run pytest -x -v --config config.json

# Run a specific test
cd tests/dev_e2e && uv run pytest -x -v --config config.json test_basic_replication.py -k test_push

# Run QE tests
cd tests/QE && uv run pytest -x -v --config config.json

# Run QE tests with specific marker
cd tests/QE && uv run pytest -x -v --config config.json -m sgw

# Lint
uv run ruff check tests/
uv run ruff format tests/
```

## Rules
- **Python 3.10+**: use `X | Y`, never `Union[X, Y]` or `Optional[X]`
- **All tests are async**: `async def test_*`, with `@pytest.mark.asyncio(loop_scope="session")`
- **Never hardcode URLs** — always use `cblpytest` fixtures
- **Never hand-edit `config.json`** — it is generated by setup scripts
- **Always use `self.mark_test_step()`** for test documentation/logging
- **No docstrings or comments on test methods** — the corresponding spec file (`spec/tests/`) documents the test flow via numbered steps matching `mark_test_step` calls. Helper functions and utilities should still have docstrings.
- **Tests must be platform-agnostic** — they must work with any test server platform
- Use `self.skip_if_not_platform()` or `self.skip_if_cbl_not()` for platform-specific behavior
- **⚠️ DO NOT create markdown documentation files** for code changes. Markdown files are for AI understanding only. The code itself is self-documenting via `spec/tests/` specifications and comments.

## Cross-References

| What | Where |
|------|-------|
| Test framework | `client/src/cbltest/` |
| API spec | `spec/api/api.yaml` |
| Test specs (dev_e2e) | `spec/tests/dev_e2e/` |
| Test specs (QE) | `spec/tests/QE/` |
| Datasets | `dataset/sg/` |
| CI pipelines | `jenkins/pipelines/{dev_e2e,QE}/` |
| Config schema | `https://packages.couchbase.com/couchbase-lite/testserver.schema.json` |

