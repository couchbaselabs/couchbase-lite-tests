# Test Suites — `tests/`

The Python test suites that exercise Couchbase Lite via the `cbltest` framework. Tests issue REST calls to per-platform test servers, which execute CBL operations against Sync Gateway (SGW) and Couchbase Server (CBS).

## Scope

You own everything under `tests/`:
- `tests/functional/` — functional tests (plus a `test_replication_filter_data.py` data helper); pipelines pick their slice by `min_*` marker, not by folder
- `tests/p2p/` — peer-to-peer tests: multipeer replicator (`test_basic_multipeer.py`, `test_multipeer.py`) and listener-based replication (`test_peer_to_peer.py`, `test_peer_to_peer_topology.py`, `test_no_conflicts.py`); they need 2–6 test servers
- `tests/system/` — system tests (`test_system_multipeer.py`, `edge_server/test_system.py`)
- `tests/upgrade_sgw/` — Sync Gateway upgrade tests (`upg_sgw` marker)
- `tests/shared/` — helpers shared across suites (e.g. `upgrade_test_helpers.py`)
- `tests/.tools/` — binary tools used during tests (`cbbackupmgr`, `bucketpool`)

You do **not** own `client/`, `servers/`, `environment/`, or `jenkins/`, but you understand how they wire into your tests.

## Layout

```
tests/
├── functional/                         # Functional tests
│   ├── conftest.py                     # dataset_path fixture (../../dataset/sg)
│   ├── config.json                     # Generated — DO NOT hand-edit
│   ├── config.example.json
│   ├── test_*.py                       # CBL, SGW and Edge Server feature tests
│   ├── test_replication_filter_data.py # Data helper for filter tests
│   └── edge_server_config/             # Edge Server configs the tests load (SCRIPT_DIR / "edge_server_config")
│
├── p2p/                                # Peer-to-peer tests (2–6 test servers)
│   ├── conftest.py                     # Same dataset_path fixture
│   ├── config.json                     # Generated — DO NOT hand-edit
│   ├── test_basic_multipeer.py         # Multipeer replicator
│   ├── test_multipeer.py
│   ├── test_peer_to_peer.py            # Listener-based replication
│   ├── test_peer_to_peer_topology.py
│   └── test_no_conflicts.py
│
├── system/                             # System tests
│   ├── conftest.py                     # Same dataset_path fixture
│   ├── config.json                     # Generated — DO NOT hand-edit
│   ├── test_system_multipeer.py
│   ├── test_system.py                  # Edge Server system test
│   └── edge_server_config/
│
├── upgrade_sgw/                        # Sync Gateway upgrade tests
│   ├── conftest.py                     # Same dataset_path fixture
│   ├── config.json                     # Generated — DO NOT hand-edit
│   ├── test_upg_sgw.py
│   └── test_rolling_upgrade_sgw.py
│
├── shared/                             # Helpers shared across suites
│   ├── jwt_helper.py
│   ├── multipeer_test_helpers.py
│   └── upgrade_test_helpers.py
│
└── .tools/
    ├── cbbackupmgr/                    # Couchbase Backup Manager binary
    └── bucketpool/                     # Bucket purge helper binary
```

## Test Pattern (use this exact shape)

```python
from pathlib import Path
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.replicator import Replicator, ReplicatorCollectionEntry, ReplicatorType
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
)


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestFeatureName(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_something(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Reset SG and load `names` dataset")
        cluster = cblpytest.clusters[0]
        await cluster.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset local database, and load `names` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="names")
        db = dbs[0]

        self.mark_test_step("Start a replicator …")
        replicator = Replicator(db, cblpytest.sync_gateways[0].replication_url("names"), ...)
        await replicator.start()

        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None

        # Resets local CBL state. SGW/CBS buckets are handled globally by cluster_cleanup.
        await cblpytest.test_servers[0].cleanup()
```

## Fixtures

| Fixture | Scope | Provided By | Purpose |
|---|---|---|---|
| `cblpytest` | session (auto) | `cbltest.plugins.cblpytest_fixture` | Top-level entry: `.test_servers`, `.sync_gateways`, `.couchbase_servers`, `.edge_servers` (each an `EdgeServerManager`), `.load_balancers`, `.request_factory` |
| `dataset_path` | session | per-suite `conftest.py` | `Path` to `dataset/sg/` |
| `cluster_cleanup` | function (autouse) | `cbltest.plugins.cluster_cleanup` (framework-wide entry point) | Resets every Edge Server, then removes all SGW databases + CBS/Rosmar buckets, before every test |

## Markers

| Marker | Use For |
|---|---|
| `@pytest.mark.sgw` | Sync Gateway feature |
| `@pytest.mark.cbl` | Couchbase Lite feature only |
| `@pytest.mark.upg_sgw` | SGW upgrade scenarios |
| `@pytest.mark.min_test_servers(N)` | Topology: ≥ N test servers |
| `@pytest.mark.min_sync_gateways(N)` | Topology: ≥ N SGW |
| `@pytest.mark.min_couchbase_servers(N)` | Topology: ≥ N CBS |
| `@pytest.mark.min_load_balancers(N)` | Topology: ≥ N load balancers |
| `@pytest.mark.min_edge_servers(N)` | Topology: ≥ N edge servers |
| `@pytest.mark.asyncio(loop_scope="session")` | **Required on every async test** |

## Suites

| Suite | Contents | Run by |
|---|---|---|
| `functional/` | Feature tests for CBL, SGW, P2P and Edge Server | `jenkins/pipelines/functional/`: platform pipelines (`-m min_test_servers`), `sgw` (`-m min_sync_gateways`), `es` (`-m min_edge_servers`) |
| `p2p/` | Peer-to-peer scenarios: multipeer replicator and listener replication (2–6 test servers) | `p2p` (several test servers in one topology) |
| `system/` | Long-running system scenarios | No scheduled pipeline yet |
| `upgrade_sgw/` | SGW upgrade scenarios (`upg_sgw` marker) | `upg-sgw` |

Specs still live under `spec/tests/dev_e2e/` (`NNN-feature.md`) and `spec/tests/QE/` (`test_feature.md`), named for the suite a test came from.

## Framework Classes You'll Use Most

| Class | Import | Use For |
|---|---|---|
| `CBLTestClass` | `cbltest.api.cbltestclass` | Base class — `mark_test_step()`, `skip_if_*()` |
| `CouchbaseCluster` | `cbltest.api.cluster` | Configure datasets on SGW + CBS |
| `Replicator`, `ReplicatorCollectionEntry`, `ReplicatorType` | `cbltest.api.replicator` | Start/stop/wait replication |
| `ReplicatorActivityLevel`, `ReplicatorBasicAuthenticator` | `cbltest.api.replicator_types` | Replicator state + auth |
| `Database`, `SnapshotUpdater` | `cbltest.api.database` | CRUD, snapshot, verify, queries, `async with db.batch_updater()` |
| `Listener` | `cbltest.api.listener` | P2P passive listener |
| `MultipeerReplicator` | `cbltest.api.multipeer_replicator` | Multi-device mesh sync |
| `SyncGateway`, `DatabaseConfig`, `DocumentUpdateEntry` | `cbltest.api.syncgateway` | SGW admin API |
| `CouchbaseServer` | `cbltest.api.couchbaseserver` | CBS bucket/scope/collection mgmt |
| `ServerVariant` | `cbltest.responses` | Platform checks (`C`, `DOTNET`, `JAVA`, `JS`) |

## Datasets

Located in `dataset/sg/`. Each has a `-sg.json` (data) and `-sg-config.json` (SGW config):
`names`, `travel`, `posts`, `todo`, `short_expiry`, `upgrade`.

## Rules

- **Python 3.13+** — modern syntax enforced by ruff `UP` + pyupgrade (see root [AGENTS.md](../AGENTS.md)).
- **All tests async** — `async def test_*` with `@pytest.mark.asyncio(loop_scope="session")`.
- **Never hardcode URLs** — pull from `cblpytest` fixtures.
- **Never hand-edit `config.json`** — generated by Jenkins setup scripts.
- **Always call `self.mark_test_step()`** for every logical step — drives test logging and tracing.
- **No docstrings or inline step descriptions on test methods** — the matching `spec/tests/**.md` file is the source of truth for the test flow; `mark_test_step()` text mirrors its numbered steps. Helper functions still need docstrings.
- **Platform-agnostic** — must work on every test server (C, .NET, iOS, Android, JVM, JS, React Native). Use `self.skip_if_not_platform()` for platform-specific behavior.
- **Feature gates** — gate on a feature, not on platforms or versions: `self.skip_if_not_supports(server, CouchbaseLiteFeature.MULTIPEER)` / `self.skip_if_sgw_not_supports(sg, SyncGatewayFeature.VERSION_VECTORS)`. Branch on a feature with `await server.supports(...)` or `await sg.supports(...)`. Add a `CouchbaseLiteFeature` or `SyncGatewayFeature` member for a new feature.
- **Version gates** — only for a bug in specific versions: `self.skip_if_cbl_not(server, ">= 3.3.0")` / `self.skip_if_sgw_not(sg, ">= 4.0.9")`, with the ticket in `reason`. `skip_if_cbl_not` ignores CBL JS and React Native (1.x versions); gate CBL JS with `skip_if_cbl_js_not`.
- **Never give a document a top-level property starting with `ts_`** — the WebSocket test servers (JS, React Native) mix their `ts_*` metadata into response bodies and the client strips it, so such properties are lost or break the request. See [servers/AGENTS.md](../servers/AGENTS.md).
- **Never put a document in the `*` channel** — not through a `channels` property, nor a sync function. Sync Gateway already gives every document to `*`, so use a named channel.
- **Prefer named channels for user access** — unless the test checks `*` access, do not grant `*` to a user. Grant the channels that the test documents use.
- **Check the spec first** — every new/modified test must align with `spec/tests/`. Add or update the spec before changing the code.
- **No markdown sidecars for code changes** — do not create `ENHANCEMENT_*.md`, `IMPLEMENTATION_*.md`, etc. PR descriptions cover motivation; the spec covers behavior.

## Commands

```bash
# Full suites
cd tests/functional  && uv run pytest -x -v --config config.json
cd tests/system      && uv run pytest -x -v --config config.json
cd tests/upgrade_sgw && uv run pytest -x -v --config config.json

# Targeted runs
cd tests/functional && uv run pytest -x -v --config config.json -k test_push
cd tests/functional && uv run pytest -x -v --config config.json test_xattrs.py
cd tests/functional && uv run pytest -x -v --config config.json -m sgw

# Lint & format
uv run ruff check tests/
uv run ruff format tests/
```

### Hunting a flake

`pytest-repeat` and `pytest-randomly` come with the default install. For these suites shuffling is
opt-in — the root `pyproject.toml` carries `addopts = "-p no:randomly"` — so an ordinary run stays in
file order and `-p randomly` turns the shuffling on. `client/tests` has its own config and shuffles.

```bash
# Repeat one test 20 times, stopping at the first failure
cd tests/functional && uv run pytest -x -v --config config.json test_basic_replication.py -k test_push --count=20

# Shuffle the order to expose leakage between tests; replay a failure with the seed it printed
cd tests/functional && uv run pytest -v --config config.json -m sgw -p randomly
cd tests/functional && uv run pytest -v --config config.json -m sgw -p randomly --randomly-seed=4250359956
```

- `--count=N` repeats each selected test N times in place. `--repeat-scope=session` repeats the whole
  selection instead, which is what reproduces a flake that needs another test to run in between.
- `--randomly-seed=N` needs `-p randomly` alongside it, since the option only exists while the plugin
  is loaded. The seed line (`Using --randomly-seed=…`) is the only way back to a shuffled order, so
  capture it with the failure.

## Cross-References

| What | Where | Relationship |
|---|---|---|
| Test framework | [client/src/cbltest/](../client/src/cbltest/) | Provides every fixture / API class |
| API contract | [spec/api/api.yaml](../spec/api/api.yaml) | Defines the REST API test servers implement |
| Test specs (dev_e2e) | [spec/tests/dev_e2e/](../spec/tests/dev_e2e/) | Behavior contracts mirroring `mark_test_step` |
| Test specs (QE) | [spec/tests/QE/](../spec/tests/QE/) | Same, for tests that came from QE |
| Datasets | [dataset/sg/](../dataset/sg/) | JSON data + SGW configs used in tests |
| CI pipelines | [jenkins/pipelines/functional/](../jenkins/pipelines/functional/), [jenkins/pipelines/upg-sgw/](../jenkins/pipelines/upg-sgw/), [jenkins/pipelines/p2p/](../jenkins/pipelines/p2p/) | Drive these tests per platform |
| Config schema | `https://packages.couchbase.com/couchbase-lite/testserver.schema.json` | Validates `config.json` |
