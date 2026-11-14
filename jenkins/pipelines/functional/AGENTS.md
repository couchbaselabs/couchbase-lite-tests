# Agent: Functional Test Pipelines (jenkins/pipelines/functional/)

## Identity

You maintain the pipelines that run `tests/functional`. Each CBL platform pipeline (Jenkins job
`e2e-functional-<platform>`) replaced a former `dev_e2e`/`QE` pair; `../main/cbl/` starts it daily for
the latest build of every CBL train. `sgw/` and `es/` select the same suite by product instead of
by CBL platform.

## Scope

You own all code under `jenkins/pipelines/functional/`:
- CBL platforms: `android/`, `c/`, `dotnet/`, `ios/`, `java/` (`desktop/` + `webservice/`), `javascript/`
- `sgw/` — every test marked `min_sync_gateways`, on a multi-SGW topology (5 SGWs over 3 CBS
  clusters, a load balancer, and a `c_macos` test server). Triggered by `../main/sgw/`. Skips
  `test_replication_xdcr.py` (CBL-8686) and collects sgcollect/cbcollect on failure.
- `es/` — every test marked `min_edge_servers` (or, with `JS_REPLICATION_TESTS_ONLY`, those also
  marked `min_test_servers`). Does NOT use the shared `setup_test()`: its own
  `generate_topology()` fills the one `topology.json` (3 Edge Servers, 1 Sync Gateway, 1 Couchbase
  Server, a localhost JS test server) with the ES/SGW/CBL versions and the latest GA Couchbase Server.
  Triggered by `../main/es/` (Jenkins job `es-functional`) against GA CBL-JS and Sync Gateway.
  Its `STRESS` checkbox runs the stress tests marked `min_edge_servers` (`tests/functional/stress/`)
  instead, with a 25-hour timeout.

You do NOT own the test code (`tests/functional/`) or the trigger jobs (`../main/cbl/`, `../main/sgw/`, `../main/es/`),
but you provision the infrastructure the tests need and accept the parameters the triggers send.

## Shared Shape

Every functional pipeline has one product under test, whose version is required. The other products'
versions are optional, and an empty one means their latest release:

| Pipeline | Under test (required) | Optional |
|---|---|---|
| CBL platforms (`android/`, `c/`, `dotnet/`, `ios/`, `java/`, `javascript/`) | `CBL_VERSION` | `SGW_VERSION`, `ES_VERSION` |
| `sgw/` | `SGW_VERSION` | `CBL_VERSION` (CBL C; empty: the latest release of the SGW's major version), `ES_VERSION` |
| `es/` | `ES_VERSION` | `SGW_VERSION`, and `CBL_VERSION` for its CBL-JS test server (empty: latest GA release) |

Every version takes the same forms: `4` or `4.1` (a train), `4.1.0` (its newest build) or
`4.1.0-18` (that build). A train resolves to its newest version, prereleases included only for the
product under test. `shared/productVersions.groovy` does this for the CBL platform and `sgw/`
pipelines: it requires the version under test, resolves all three versions, rejects an incompatible
CBL/SGW pair (`shared/cblSgwCompatibility.groovy`) or CBL/dataset pair, and sets `CBL_RESOLVED`,
`SGW_RESOLVED`, `ES_RESOLVED`, and `CBL_PREBUILD_VERSION`/`CBL_PREBUILD_BUILD` for the prebuild job.
The Edge Server version reaches the topology through the run scripts' `--es-version` (`-EsVersion` in
PowerShell) and `setup_test.py --es-version`.

Datasets: CBL platforms, `sgw/` and `multiplatform` take an explicit `TS_DATASET_VERSION` (`4.0` or
`3.2`), and fail at Init when their CBL cannot open it (`shared/cblDatasetCompatibility.groovy`: CBL 3.x
needs 3.2, CBL 4.x can use either). The daily triggers pass the dataset of the CBL major version. CBL JS
(`javascript/`) and `es/` always use 3.2, so they have no dataset parameter.

The CBL platform pipelines also share:

- **Parameters:** besides the versions, `TS_DATASET_VERSION` (not on `javascript/`), `TS_TEST_FILTER`
  (pytest `-k`; disables result upload), `RUN_PREBUILD`, plus `RUN_*` checkboxes on multi-target pipelines.
- **Test selection:** `-m min_test_servers` on `tests/functional` (`sgw/`: `-m min_sync_gateways`;
  `es/`: `-m min_edge_servers`). Tests whose other `min_*`
  markers the topology can't satisfy are skipped by the `required_topology` plugin.
  `java/webservice/` runs only `test_basic_replication.py`, since desktop runs the full suite.
- **Scripts:** `test.sh`/`run_test.sh` accept `--setup-only`; the PowerShell scripts accept `-SetupOnly`.
- **Artifacts:** each stage sets `TS_ARTIFACTS_DIR`; teardown's `move_artifacts` moves logs into
  `tests/functional/$TS_ARTIFACTS_DIR/`, which the stage archives.
- **Locks:** device nodes lock on the node name (`mob-e2e-iphone-03`, `mob-e2e-android-01`,
  `net-windows`); pooled hosts (`e2e&&macos-host`, `e2e&&linux-host`, `e2e&&windows-host`) lock on
  `env.NODE_NAME`, because the test server binds fixed localhost ports.

## CBL Backend (`cbl_topology_backend.json`)

Every CBL platform topology (`android/`, `c/`, `dotnet/`, `ios/`, `java/`, `javascript/`) declares only
its test server(s) and includes `cbl_topology_backend.json`, which is sized so every `tests/functional`
test marked `min_test_servers` can run. `sgw/` and `es/` do not use it: they select tests by a
different marker and keep their own topologies.

| Resource | Layout | Needed by |
|---|---|---|
| Clusters | 3 clusters × 1 Couchbase Server node | `test_isgr_load_balancer.py` (`min_clusters(3)`), `test_replication_xdcr.py` (2) |
| Sync Gateways | one per cluster (0, 1, 2) | ISGR uses the SGWs of clusters 1 and 2; XDCR clusters 0 and 1 |
| Load balancers | LB 0 → SGW 0; LB 1 → SGWs 1, 2 | XDCR replicates through LB 0; ISGR pins `sg-0`/`sg-1` behind LB 1 |
| Edge Servers | 1 (latest GA unless the topology sets `defaults.es.version`) | Edge Server tests that replicate with a CBL test server |

Change the CBL backend there, not per platform. `shared/setup_test.py` re-roots any relative `include`
for the generated topology, so the include can live outside `environment/aws/topology_setup/`.

Every platform topology has one test server, so tests that need more live in `tests/multiplatform`
and run in the `multiplatform` pipeline.

## Topology-Test Synchronization

Every test declares the infrastructure it needs with `@pytest.mark.min_*` markers. The pipeline's
topology must provide at least that much, or the test is skipped (never silently run short).
When a test needs more than these single-test-server topologies provide, it belongs in a pipeline
with a bigger topology (for example `sgw/` or `upg-sgw/`), not in a larger platform topology.

## Coding Rules

- **`setup_dir` omitted** in `setup_test.py` (defaults to `"functional"`).
- **Never hand-edit generated topology or `config.json`** — `setup_test.py` writes them at runtime.
- **Validate topology against schema** — `environment/aws/topology_setup/topology_schema.json`.
- **Python 3.13+**: `X | Y`, never `Union[X, Y]`.
- **Do not create markdown documentation files** for changes.

## Commands

```bash
# Set up the backend and test server only (no tests)
jenkins/pipelines/functional/ios/test.sh 4.0.0 4 --setup-only

# Teardown
jenkins/pipelines/functional/ios/teardown.sh
```

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| Parent pipelines docs | `../AGENTS.md`, `../../AGENTS.md` | Higher-level pipeline documentation |
| Functional test suite | `../../../tests/functional/` | Source of `@pytest.mark.min_*` requirements |
| Test specifications | `../../../spec/tests/` | Define expected behavior |
| Shared setup | `../shared/setup_test.py` | `setup_test()` every pipeline delegates to |
| Triggers | `../main/cbl/`, `../main/sgw/`, `../main/es/` | Start these jobs for new builds |
