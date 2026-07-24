# Test Suites — `tests/`

The two Python test suites that exercise Couchbase Lite via the `cbltest` framework. Tests issue REST calls to per-platform test servers, which execute CBL operations against Sync Gateway (SGW) and Couchbase Server (CBS).

## Scope

You own everything under `tests/`:
- `tests/dev_e2e/` — Developer E2E tests, split into `cbl/` (CBL suite) and `edge_server/` (Edge Server sub-suite, ES-versioned)
- `tests/QE/` — QA suite, including an edge-server sub-suite
- `tests/shared/` — helpers shared across suites (e.g. `upgrade_test_helpers.py`)
- `tests/.tools/` — binary tools used during tests (e.g. `cbbackupmgr`)

You do **not** own `client/`, `servers/`, `environment/`, or `jenkins/`, but you understand how they wire into your tests.

## Layout

```
tests/
├── dev_e2e/                            # Developer E2E
│   ├── conftest.py                     # dataset_path fixture (../../dataset/sg) — shared by both sub-suites
│   ├── config.json                     # Generated — DO NOT hand-edit
│   ├── config.example.json
│   ├── cbl/                            # CBL test suite (run by the per-platform jobs)
│   │   ├── test_basic_replication.py
│   │   ├── test_replication_filter.py
│   │   ├── test_replication_filter_data.py # Data helper for filter tests
│   │   ├── test_replication_auto_purge.py
│   │   ├── test_replication_blob.py
│   │   ├── test_replication_behavior.py
│   │   ├── test_replication_upgrade.py
│   │   ├── test_replication_xdcr.py
│   │   ├── test_custom_conflict.py
│   │   ├── test_encrypted_properties.py
│   │   ├── test_fest.py
│   │   ├── test_multipeer.py
│   │   └── test_query_consistency.py
│   └── edge_server/                    # Edge Server sub-suite (separate ES job; ES-versioned)
│       ├── jwt_helper.py
│       ├── test_jwt_simple.py
│       └── test_jwt_rotation.py
│
├── QE/                                 # QA — broader coverage + edge cases
│   ├── conftest.py                     # dataset_path + cleanup_after_test (autouse)
│   ├── config.json                     # Generated — DO NOT hand-edit
│   ├── test_db_gone.py
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
│   ├── test_replication_upgrade_delta_sync.py
│   ├── test_replicator_encryption_hook.py
│   ├── test_rolling_upgrade_sgw.py
│   ├── test_server_setup.py
│   ├── test_system_multipeer.py
│   ├── test_ttl.py
│   ├── test_upg_sgw.py
│   ├── test_users_channels.py
│   ├── test_xattrs.py
│   └── edge_server/                    # Edge Server sub-suite
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
├── shared/                              # Helpers shared across dev_e2e/QE
│   └── upgrade_test_helpers.py
│
└── .tools/
    └── cbbackupmgr/                    # Couchbase Backup Manager binary
```

## Test Pattern (use this exact shape)

```python
from pathlib import Path
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.replicator import Replicator, ReplicatorCollectionEntry, ReplicatorType
from cbltest.api.replicator_types import ReplicatorActivityLevel, ReplicatorBasicAuthenticator


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestFeatureName(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_something(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = CouchbaseCloud([cblpytest.sync_gateways[0]], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset local database, and load `names` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="names")
        db = dbs[0]

        self.mark_test_step("Start a replicator …")
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("names"), ...)
        await replicator.start()

        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None

        # dev_e2e: manual cleanup. QE: handled by cleanup_after_test.
        await cblpytest.test_servers[0].cleanup()
```

## Fixtures

| Fixture | Scope | Provided By | Purpose |
|---|---|---|---|
| `cblpytest` | session (auto) | `cbltest.plugins.cblpytest_fixture` | Top-level entry: `.test_servers`, `.sync_gateways`, `.couchbase_servers`, `.edge_servers`, `.load_balancers`, `.request_factory` |
| `dataset_path` | session | per-suite `conftest.py` | `Path` to `dataset/sg/` |
| `cleanup_after_test` | function (autouse, QE only) | `tests/QE/conftest.py` | Cleans up SGW DBs + CBS buckets after every `@pytest.mark.sgw` test |

## Markers

| Marker | Use For |
|---|---|
| `@pytest.mark.sgw` | Sync Gateway feature (QE: triggers auto-cleanup) |
| `@pytest.mark.cbl` | Couchbase Lite feature only |
| `@pytest.mark.upg_sgw` | SGW upgrade scenarios |
| `@pytest.mark.min_test_servers(N)` | Topology: ≥ N test servers |
| `@pytest.mark.min_sync_gateways(N)` | Topology: ≥ N SGW |
| `@pytest.mark.min_couchbase_servers(N)` | Topology: ≥ N CBS |
| `@pytest.mark.min_load_balancers(N)` | Topology: ≥ N load balancers |
| `@pytest.mark.min_edge_servers(N)` | Topology: ≥ N edge servers |
| `@pytest.mark.asyncio(loop_scope="session")` | **Required on every async test** |

## dev_e2e vs QE

| Aspect | dev_e2e | QE |
|---|---|---|
| Audience | CBL release validation | QA regression |
| Cleanup | manual `await ts.cleanup()` | autouse `cleanup_after_test` |
| Markers | topology only | `sgw` / `cbl` + topology |
| Edge Server | `edge_server/` sub-suite (separate ES-versioned job) | `edge_server/` sub-suite |
| SGW upgrade | `test_replication_upgrade.py` | `test_upg_sgw.py` |
| Multi-SGW | `test_replication_xdcr.py` (2 SGW + 2 CBS + LB) | `test_users_channels.py` (3+ SGW), `test_high_availability.py` |
| Spec location | `spec/tests/dev_e2e/NNN-feature.md` | `spec/tests/QE/test_feature.md` |

## Framework Classes You'll Use Most

| Class | Import | Use For |
|---|---|---|
| `CBLTestClass` | `cbltest.api.cbltestclass` | Base class — `mark_test_step()`, `skip_if_*()` |
| `CouchbaseCloud` | `cbltest.api.cloud` | Configure datasets on SGW + CBS |
| `Replicator`, `ReplicatorCollectionEntry`, `ReplicatorType` | `cbltest.api.replicator` | Start/stop/wait replication |
| `ReplicatorActivityLevel`, `ReplicatorBasicAuthenticator` | `cbltest.api.replicator_types` | Replicator state + auth |
| `Database`, `SnapshotUpdater` | `cbltest.api.database` | CRUD, snapshot, verify, queries, `async with db.batch_updater()` |
| `Listener` | `cbltest.api.listener` | P2P passive listener |
| `MultipeerReplicator` | `cbltest.api.multipeer_replicator` | Multi-device mesh sync |
| `SyncGateway`, `PutDatabasePayload`, `DocumentUpdateEntry` | `cbltest.api.syncgateway` | SGW admin API |
| `CouchbaseServer` | `cbltest.api.couchbaseserver` | CBS bucket/scope/collection mgmt |
| `ServerVariant` | `cbltest.responses` | Platform checks (`C`, `DOTNET`, `JAVA`, `JS`) |

## Datasets

Located in `dataset/sg/`. Each has a `-sg.json` (data) and `-sg-config.json` (SGW config):
`names`, `travel`, `posts`, `todo`, `short_expiry`, `upgrade`.

## Rules

- **Python 3.10+** — `X | Y`, never `Union[X, Y]` / `Optional[X]`.
- **All tests async** — `async def test_*` with `@pytest.mark.asyncio(loop_scope="session")`.
- **Never hardcode URLs** — pull from `cblpytest` fixtures.
- **Never hand-edit `config.json`** — generated by Jenkins setup scripts.
- **Always call `self.mark_test_step()`** for every logical step — drives test logging and tracing.
- **No docstrings or inline step descriptions on test methods** — the matching `spec/tests/**.md` file is the source of truth for the test flow; `mark_test_step()` text mirrors its numbered steps. Helper functions still need docstrings.
- **Platform-agnostic** — must work on every test server (C, .NET, iOS, JVM, JS). Use `self.skip_if_not_platform()` for platform-specific behavior.
- **Version gates** — use `self.skip_if_cbl_not(server, ">= 3.3.0")` / `self.skip_if_sgw_not(sg, ">= 4.0.0")` rather than runtime checks.
- **Check the spec first** — every new/modified test must align with `spec/tests/`. Add or update the spec before changing the code.
- **No markdown sidecars for code changes** — do not create `ENHANCEMENT_*.md`, `IMPLEMENTATION_*.md`, etc. PR descriptions cover motivation; the spec covers behavior.

## Commands

```bash
# Full suites
cd tests/dev_e2e && uv run pytest -x -v --config config.json
cd tests/QE      && uv run pytest -x -v --config config.json

# Targeted runs
cd tests/dev_e2e && uv run pytest -x -v --config config.json -k test_push
cd tests/QE      && uv run pytest -x -v --config config.json test_xattrs.py
cd tests/QE      && uv run pytest -x -v --config config.json -m sgw

# Lint & format
uv run ruff check tests/
uv run ruff format tests/
```

## Cross-References

| What | Where | Relationship |
|---|---|---|
| Test framework | [client/src/cbltest/](../client/src/cbltest/) | Provides every fixture / API class |
| API contract | [spec/api/api.yaml](../spec/api/api.yaml) | Defines the REST API test servers implement |
| Test specs (dev_e2e) | [spec/tests/dev_e2e/](../spec/tests/dev_e2e/) | Behavior contracts mirroring `mark_test_step` |
| Test specs (QE) | [spec/tests/QE/](../spec/tests/QE/) | Same, for QE tests |
| Datasets | [dataset/sg/](../dataset/sg/) | JSON data + SGW configs used in tests |
| CI pipelines | [jenkins/pipelines/dev_e2e/](../jenkins/pipelines/dev_e2e/), [jenkins/pipelines/QE/](../jenkins/pipelines/QE/) | Drive these tests per platform |
| Config schema | `https://packages.couchbase.com/couchbase-lite/testserver.schema.json` | Validates `config.json` |
