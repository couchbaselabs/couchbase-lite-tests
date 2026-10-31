# Test Suites — `tests/`

The two Python test suites that exercise Couchbase Lite via the `cbltest` framework. Tests issue REST calls to per-platform test servers, which execute CBL operations against Sync Gateway (SGW) and Couchbase Server (CBS).

## Scope

You own everything under `tests/`:
- `tests/dev_e2e/` — Developer E2E tests (plus a `test_replication_filter_data.py` data helper)
- `tests/QE/` — QA suite, including an edge-server sub-suite
- `tests/shared/` — helpers shared across suites (e.g. `upgrade_test_helpers.py`)
- `tests/.tools/` — binary tools used during tests (`cbbackupmgr`, `bucketpool`)

You do **not** own `client/`, `servers/`, `environment/`, or `jenkins/`, but you understand how they wire into your tests.

## Layout

```
tests/
├── dev_e2e/                            # Developer E2E
│   ├── conftest.py                     # dataset_path fixture (../../dataset/sg)
│   ├── config.json                     # Generated — DO NOT hand-edit
│   ├── config.example.json
│   ├── test_basic_replication.py
│   ├── test_replication_filter.py
│   ├── test_replication_filter_data.py # Data helper for filter tests
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
├── QE/                                 # QA — broader coverage + edge cases
│   ├── conftest.py                     # dataset_path fixture (../../dataset/sg)
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
| Cleanup | autouse `cluster_cleanup` + manual `await ts.cleanup()` | autouse `cluster_cleanup` |
| Markers | topology only | `sgw` / `cbl` + topology |
| Edge Server | — | `edge_server/` sub-suite |
| SGW upgrade | `test_replication_upgrade.py` | `test_upg_sgw.py` |
| Multi-SGW | `test_replication_xdcr.py` (2 SGW + 2 CBS + LB) | `test_users_channels.py` (3+ SGW), `test_high_availability.py` |
| Spec location | `spec/tests/dev_e2e/NNN-feature.md` | `spec/tests/QE/test_feature.md` |

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

## OpenAPI Conformance Tests (schemathesis)

[schemathesis](https://schemathesis.readthedocs.io/) generates requests from a product's OpenAPI spec and checks
each response against that spec. `tests/dev_e2e/syncgateway/test_admin_api_schema.py` (Sync Gateway admin API) and
`tests/QE/edge_server/test_public_api_schema.py` (Edge Server public API) follow this pattern: copy their shape for
any other REST API.

### The pattern

1. **Fetch the spec for the version under test.** Never vendor it into this repo.
2. **Start a server with real data**, then pin every path parameter that names a database (`{db}`, `{keyspace}`)
   in `[parameters]`. Otherwise almost every request is a 404.
3. **Run the `schemathesis` CLI with `cbltest.schemathesis.run_schemathesis`**, which passes `--config-file`,
   `--url`, `--auth` and one `--include-name "METHOD /path"` per operation in scope. Assert that the exit code is 0.
4. **Keep the configuration in a `schemathesis.toml` beside the test.** Set `seed`, `deterministic = true` and
   `database = "none"`, so that every run sends the same requests.
5. **Add operations a few at a time.** For each new failure, reproduce it with `curl` first. Then add one
   `[[operations]]` entry per operation that turns off only the failing check. Start its comment with
   `Spec:` (the spec is wrong), `Bug:` (the server is wrong) or `Harness:` (cbltest causes it), and end it with
   the ticket key once one is filed, for example `(CBL-9281)`. Schemathesis has no field for a note and does not
   report disabled checks, so the comment is the only record.

### Gotchas (schemathesis 4.x)

- **Pass the generation mode with `run_schemathesis(mode=...)`**, which sends `--mode`. The top-level
  `[generation] mode` does not reach the coverage and fuzzing phases, and a mode set on a phase overrides
  `--mode`. Edge Server sets no mode in its config, and runs once per mode. Sync Gateway sets `positive` on every
  phase. Also set `[phases.coverage] unexpected-methods = []`, so that coverage does not probe methods the spec
  does not list.
- **Set `request-timeout`**, so that a request the server never answers fails fast and does not stall the run.
- **Do not use hooks to filter cases.** `filter_case` hooks skip the cases that the coverage phase builds. Use
  `[[operations]]` entries and `parameters = {...}` pins instead.
- **Pin parameters that hold a request open**, for example `feed = "normal"` on `_changes`. A body field cannot
  be pinned in every phase, so leave out an operation whose `feed` is in the body.
- **Do not use `--baseline`.** Random multipart boundaries change the failure signatures on every run.
- **Pin a header with its location**, for example `parameters = { "header.If-Match" = "*" }`.
- **A known 500 turns off `not_a_server_error` for the whole operation.** If one parameter value causes the
  500, pin that parameter instead, for example `revs_limit = 20` on Sync Gateway `_bulk_get`.

### Local run

Mark each conformance test `@pytest.mark.openapi`. `scripts/run_openapi_tests.sh --es-version 1.1.1-0` runs
every marked test on this host. It starts Sync Gateway on rosmar and Edge Server in Docker, runs both suites, and
stops both servers. It needs no Couchbase Server and no test server. `--sgw-only` and `--es-only` run one suite,
`--keep` leaves the servers running, and arguments after `--` go to pytest. The script stops the Sync Gateways
that this checkout started before.

### Edge Server

The test is `tests/QE/edge_server/test_public_api_schema.py`, with its spec in
`spec/tests/QE/edge_server/test_public_api_schema.md`.

- **Spec source.** The `couchbase/edge-server` repository holds the spec as `api/public.yaml` plus `$ref` files,
  but the repository is private, so CI cannot clone it. The test uses the bundled spec that the docs site publishes:
  `https://docs.couchbase.com/couchbase-edge-server/current/public-api-reference/_attachments/public.bundle.yaml`.
  It describes only the current release, so the test skips when the server's major and minor version differ from
  the spec's `info.version`.
- **Server.** `config/test_public_api_schema.json` declares the provisioned users file, because `_active_tasks`
  needs the admin role. The test signs in as `manager.admin_user`. The config also sets `enable_anonymous_users`,
  `enable_adhoc_queries`, `enable_client_writes` and the `female_ids` named query. The query has no
  parameters, because a named query rejects any parameter it does not declare, and the spec cannot list them.
- **Parameters.** `db` is pinned to the `names` database, `keyspace` to `ES_OPENAPI_KEYSPACE`, and `name` to
  the named query. Pin `docid`
  to `name_1` per operation for reads. Do not pin it globally, because writes need fresh IDs. Each
  `{key}` operation pins its own document, key and dataset revision, because the spec has no links, so the
  stateful phase never chains a write to a real document. For the same reason the stateful phase is off. `If-Match` is pinned to `*` on document writes,
  because an empty header value closes the connection.
- **Batches**, one at a time with a report after each:
  1. Done. Read only: `GET /`, `GET /_all_dbs`, `GET /_active_tasks`, `GET /{keyspace}`, `GET` and `POST
     /{keyspace}/_all_docs`, `GET` and `HEAD /{keyspace}/{docid}`.
  2. Done. Writes: `PUT` and `DELETE /{keyspace}/{docid}`,
     `POST /{keyspace}/_bulk_docs`, and `GET`, `PUT` and `DELETE /{keyspace}/{docid}/{key}`. Leave out
     `PUT /{keyspace}`. The spec calls it "Create a document", but it creates a database or a collection.
  3. Done. Queries and changes: `POST /{keyspace}/_query`, `GET` and `POST /{keyspace}/_query/{name}`, and
     `GET /{keyspace}/_changes` with `feed = "normal"`. Leave out `POST _changes`, as for Sync Gateway.
  4. Done. `POST /{db}/_session`, `GET /_replicate`, and `GET` and `DELETE /_replicate/{taskid}`. The test
     starts two replications to an unreachable port on the Edge Server host, and passes their task IDs through
     `ES_OPENAPI_READ_TASK` and `ES_OPENAPI_STOP_TASK`, because task IDs change on every run. `POST /_replicate`
     is left out: a body field cannot be pinned in every phase, so Edge Server would connect to generated hosts.
  5. Done. Negative mode: the test runs once per mode, with the same operations and config. Invalid requests
     must get a 4xx. `negative_data_rejection` is off where Edge Server ignores an invalid value instead of
     rejecting it.
  6. Done. Keyspaces: `PUT /{keyspace}`, and every positive run again in `names.schema_coll` and
     `names.schema_scope.schema_coll`. Edge Server cannot create a collection through the API: `PUT /{keyspace}`
     is always a 403, because 1.1.1 never turns on `allowCreateDBs` or `allowCreateCollections`. The config
     creates the collections instead (`"create": true` and `"collections"`). The test copies `name_1` to `name_3`
     into each with `new_edits=False`, which keeps the dataset revisions that the `{key}` pins use.
- **Authorization** is not a schemathesis test. The spec declares no security schemes, and documents a 401 or
  403 only on `_session`, so schemathesis cannot know which user is allowed what.
  `test_public_api_authorization.py` sends one valid request per operation as each user, and checks the status
  against a table. `KNOWN_BUGS` holds the requests that Edge Server allows although it must not.
- **Reproducing a failure.** Run `scripts/run_openapi_tests.sh --es-only --keep`. Between runs, the teardown
  restores the provisioned config, which declares no users. To reproduce a failure with `curl` after a run, leave
  out the credentials. During a run, the admin user is `admin_user`, with the password `password`.

## Commands

```bash
# Full suites
cd tests/dev_e2e && uv run pytest -x -v --config config.json
cd tests/QE      && uv run pytest -x -v --config config.json

# Targeted runs
cd tests/dev_e2e && uv run pytest -x -v --config config.json -k test_push
cd tests/QE      && uv run pytest -x -v --config config.json test_xattrs.py
cd tests/QE      && uv run pytest -x -v --config config.json -m sgw

# OpenAPI conformance tests on local rosmar Sync Gateway and Docker Edge Server
scripts/run_openapi_tests.sh --es-version 1.1.1-0

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
cd tests/dev_e2e && uv run pytest -x -v --config config.json test_basic_replication.py -k test_push --count=20

# Shuffle the order to expose leakage between tests; replay a failure with the seed it printed
cd tests/QE && uv run pytest -v --config config.json -m sgw -p randomly
cd tests/QE && uv run pytest -v --config config.json -m sgw -p randomly --randomly-seed=4250359956
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
| Test specs (QE) | [spec/tests/QE/](../spec/tests/QE/) | Same, for QE tests |
| Datasets | [dataset/sg/](../dataset/sg/) | JSON data + SGW configs used in tests |
| CI pipelines | [jenkins/pipelines/dev_e2e/](../jenkins/pipelines/dev_e2e/), [jenkins/pipelines/QE/](../jenkins/pipelines/QE/) | Drive these tests per platform |
| Config schema | `https://packages.couchbase.com/couchbase-lite/testserver.schema.json` | Validates `config.json` |
