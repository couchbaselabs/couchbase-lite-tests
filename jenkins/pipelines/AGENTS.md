# Pipeline Structure — `jenkins/pipelines/`

This file covers the per-pipeline structure and the **topology-test synchronization rule** that lives here. For the full inventory of platforms, shared scripts (`setup_test.py`, `config.sh`), and Jenkinsfile patterns, see [../AGENTS.md](../AGENTS.md).

## Scope

You own everything under `jenkins/pipelines/`:
- `shared/` — `setup_test.py` (`setup_test` / `setup_test_multi`), `config.sh`, `config.psm1`
- `dev_e2e/` — developer E2E pipelines (one per platform + `multipeer_functional/`)
- `QE/` — QA pipelines (one per platform + `sgw/`, `upg-sgw/`, `es/`, `multiplatform/`)
- `prebuild/` — test server artifact prebuild pipeline

## ⚠️ Topology–Test Synchronization (most important rule)

Every test declares resource requirements via `@pytest.mark.min_*`:

```python
@pytest.mark.min_sync_gateways(2)
@pytest.mark.min_couchbase_servers(2)
@pytest.mark.min_test_servers(1)
class TestMultiNode(CBLTestClass): ...
```

The matching topology file MUST provision **at least** those resources:

```json
{
  "clusters":      [{"server_count": 1}, {"server_count": 1}],
  "sync_gateways": [{"cluster": 0},      {"cluster": 1}],
  "test_servers":  [{"platform": "swift_ios", "cbl_version": "{{version}}"}]
}
```

**If topology resources < test requirements → tests hang waiting for instances.**

When a test adds new `@pytest.mark.min_*` decorators, **update the topology file first**, then the test.

## Per-Platform Layout

Every `{platform}/` directory under `dev_e2e/` or `QE/` contains:

```
{platform}/
├── Jenkinsfile                       # Groovy pipeline definition
├── setup_test.py                     # Calls shared setup_test()/setup_test_multi()
├── config*.json                      # TDK config template(s)
├── topology*.json                    # Topology template(s)
├── test.sh / run_test.sh / run_test.ps1
├── teardown.sh / teardown.ps1
└── (platform-specific extras)
```

`setup_test.py` template + per-platform argument table → see [../AGENTS.md](../AGENTS.md).

## Topology File Rules

| Concept | Rule |
|---|---|
| **CBS–SGW pairing** | Each `sync_gateways[i].cluster` is the index into `clusters[]`. Every `cluster` entry is one CBS instance. |
| **Resource counts** | `clusters`, `sync_gateways`, `test_servers`, `edge_servers`, `load_balancers` must individually satisfy the tests' `min_*` markers. |
| **Templates** | Files use `{{placeholder}}` syntax — resolved at runtime by `setup_test.py`. |
| **Single-file topology** | Most pipelines use one `topology*.json`. |
| **Multi-file topology** | `c/`, `dotnet/` use `topologies/topology_single_{platform}.json` per-target. |
| **Programmatic topology** | `QE/es/` builds topology via `generate_topology()` instead of a JSON template. |

Common placeholders: `{{version}}`, `{{cbl_version}}`, `{{cbs_version}}`, per-platform variants like `{{swift_ios}}`, `{{jak_android}}`, `{{jak_desktop}}`.

## Special Pipelines

### `QE/upg-sgw/` — SGW upgrade

Iterates SGW versions. Requires **≥ 2 SGW nodes and ≥ 2 CBS clusters** for upgrade consistency testing. `test.sh`:

1. Initial setup at first SGW version → run `upg_sgw` tests.
2. For each subsequent version:
   - `stop_backend.py --destroy-sgw --no-ts-stop`
   - `start_backend.py --no-cbs-provision --no-es-provision --no-lb-provision --no-ls-provision --no-ts-run`
   - Re-run `upg_sgw` tests.

### `QE/es/` — Edge Server

Does NOT use shared `setup_test()`. Has its own `generate_topology()` and calls `start_backend()` directly. CLI options: `--sgw-version`, `--cbs-version`.

### `dev_e2e/multipeer_functional/` and `QE/multiplatform/`

Use `setup_test_multi()` (not `setup_test()`) with per-platform version maps for cross-platform mesh tests.

## `shared/setup_test.py` Recap

- `setup_test(cbl_version, sgw_version, topology_file_in, config_file_in, topology_tag, couchbase_version="7.6", setup_dir="dev_e2e")` — wraps all platforms with the same `cbl_version` and delegates.
- `setup_test_multi(cbl_version_map, sgw_version, …)` — reads the topology template, resolves versions via `proget`, sets defaults + tag + per-test-server CBL version, writes the final topology to `environment/aws/topology_setup/topology.json`, downloads `cbbackupmgr`, then calls `start_backend()`.
- `ts_to_topology()` maps platform tags: `swift_* → ios`, `jak_android → android`, `jak_* → java`, `dotnet_* → dotnet`, `c_* → c`.

## Rules

- **`sys.path.append(str(SCRIPT_DIR.parents[3]))`** in every `setup_test.py` (puts repo root on `sys.path`).
- **`click`** for all CLI parsing.
- **`setup_dir="QE"`** for QE pipelines; omit for dev_e2e (defaults to `"dev_e2e"`).
- **Topology/config JSONs are templates** — final versions generated at runtime, never committed.
- **Topology must match `@pytest.mark.min_*` decorators** before tests change.
- **Always call `move_artifacts`** in `teardown.sh`.
- **Teardown runs on failure** — Jenkinsfile uses `post { always { … } }`.
- **Python 3.10+** — `X | Y`, never `Union[X, Y]`.
- **No markdown sidecars** for pipeline changes.

## Commands

```bash
# Run a pipeline's setup locally
cd environment/aws
uv run ../jenkins/pipelines/dev_e2e/ios/setup_test.py 4.0.0 4.0.0
uv run ../jenkins/pipelines/QE/upg-sgw/setup_test.py 4.0.0 4.0.0

# Teardown
cd jenkins/pipelines/QE/upg-sgw && ./teardown.sh
```

## Cross-References

| What | Where | Relationship |
|---|---|---|
| Parent CI/CD doc | [../AGENTS.md](../AGENTS.md) | Higher-level pipeline documentation |
| Shared setup logic | [shared/setup_test.py](shared/setup_test.py) | Core function all pipelines delegate to |
| Test suites | [tests/dev_e2e/](../../tests/dev_e2e/), [tests/QE/](../../tests/QE/) | Source of `@pytest.mark.min_*` requirements |
| AWS orchestrator | [../../environment/aws/start_backend.py](../../environment/aws/start_backend.py) | Called by `setup_test()` |
| Topology schema | [../../environment/aws/topology_setup/topology_schema.json](../../environment/aws/topology_setup/topology_schema.json) | Validates topology JSON |
