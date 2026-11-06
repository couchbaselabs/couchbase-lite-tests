# Pipeline Structure — `jenkins/pipelines/`

This file covers the per-pipeline structure and the **topology-test synchronization rule** that lives here. For the full inventory of platforms, shared scripts (`setup_test.py`, `config.sh`), and Jenkinsfile patterns, see [../AGENTS.md](../AGENTS.md).

## Scope

You own everything under `jenkins/pipelines/`:
- `shared/` — `setup_test.py` (`setup_test`), `config.sh`, `config.psm1`, and the Groovy helpers `resolveProgetVersion`, `progetBuilds`, `triggerRecord`, `cblSgwCompatibility`
- `functional/` — pipelines that run `tests/functional`: one per CBL platform (`android/`, `c/`, `dotnet/`, `ios/`, `java/`, `javascript/`) plus `sgw/` and `es/`
- `main/` — daily triggers: `cbl/` starts `e2e-functional-<platform>` for the latest build of every CBL train; `sgw/` starts `functional/sgw`; `es/` starts `functional/es`
- `upg-sgw/` — SGW upgrade pipelines
- `multiplatform/` — multi-platform pipeline (`tests/multiplatform`, several test servers)
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
  "test_servers":  [{"platform": "swift_ios", "cbl_versions": "{{version}}"}]
}
```

**If topology resources < test requirements → tests hang waiting for instances.**

When a test adds new `@pytest.mark.min_*` decorators, **update the topology file first**, then the test.

## Per-Platform Layout

Every `{platform}/` directory under `functional/` contains:

```
{platform}/
├── Jenkinsfile                       # Groovy pipeline definition
├── setup_test.py                     # Calls shared setup_test()
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
| **Multi-file topology** | `functional/c/`, `functional/dotnet/` use `topologies/topology_single_{platform}.json` per-target. |
| **Programmatic topology** | `functional/es/` builds topology via `generate_topology()` instead of a JSON template. |

Common placeholders: `{{version}}`, `{{cbl_versions}}`, `{{cbs_version}}`, per-platform variants like `{{swift_ios}}`, `{{jak_android}}`, `{{jak_desktop}}`.

## Special Pipelines

### `upg-sgw/` — SGW upgrade

Iterates SGW versions. Requires **≥ 2 SGW nodes and ≥ 2 CBS clusters** for upgrade consistency testing. `test.sh`:

1. Initial setup at first SGW version → run `upg_sgw` tests.
2. For each subsequent version:
   - `stop_backend.py --destroy-sgw --no-ts-stop`
   - `start_backend.py --no-cbs-provision --no-es-provision --no-lb-provision --no-ls-provision --no-ts-run`
   - Re-run `upg_sgw` tests.

### `functional/es/` — Edge Server

Does NOT use shared `setup_test()`. Has its own `generate_topology()` and calls `start_backend()` directly. CLI options: `--sgw-version`, `--cbs-version`.

### `multiplatform/`

`setup_multiplatform.py` checks `PLATFORM_VERSIONS` against `topology.json` (every test server the agent can reach) and ProGet, then calls the shared `setup_test()` on just the test servers the entries use.

## `shared/setup_test.py` Recap

- `setup_test(cbl_versions, sgw_versions, topology_file_in, config_file_in, topology_tag, couchbase_version="7.6", setup_dir="functional")` — reads the topology template, resolves versions via `proget`, assigns `cbl_versions` positionally to `test_servers` and `sgw_versions` positionally to `sync_gateways` (repeating the last entry once a list is exhausted — see `distribute_versions`; `sgw_versions` only applies per-instance when `sync_gateways` is defined directly in `topology_file_in` rather than via `include`), sets defaults + tag, writes the final topology to `environment/aws/topology_setup/topology.json`, downloads `cbbackupmgr`, then calls `start_backend()`.
- `VersionType` is a `click.ParamType` that converts a comma-separated CLI argument (e.g. `"4.0.0,4.1.0"`) into a `list[str]` (via `parse_versions()`) — every `setup_test.py` CLI wrapper declares its version arguments with `type=VersionType()` so `cli_entry` receives lists directly.

## Rules

- **`sys.path.append(str(SCRIPT_DIR.parents[3]))`** in every `setup_test.py` (puts repo root on `sys.path`).
- **`click`** for all CLI parsing.
- **`setup_dir`** — omit for the `functional` suite (the default); `upg-sgw` passes `"upgrade_sgw"`.
- **Topology/config JSONs are templates** — final versions generated at runtime, never committed.
- **Topology must match `@pytest.mark.min_*` decorators** before tests change.
- **Always call `move_artifacts`** in `teardown.sh`.
- **Teardown runs on failure** — Jenkinsfile uses `post { always { … } }`.
- **Python 3.13+** — `X | Y`, never `Union[X, Y]`.
- **No markdown sidecars** for pipeline changes.

## Commands

```bash
# Run a pipeline's setup locally
cd environment/aws
uv run ../jenkins/pipelines/functional/ios/setup_test.py 4.0.0 4.0.0
uv run ../jenkins/pipelines/upg-sgw/setup_test.py 4.0.0 4.0.0

# Teardown
cd jenkins/pipelines/upg-sgw && ./teardown.sh
```

## Cross-References

| What | Where | Relationship |
|---|---|---|
| Parent CI/CD doc | [../AGENTS.md](../AGENTS.md) | Higher-level pipeline documentation |
| Shared setup logic | [shared/setup_test.py](shared/setup_test.py) | Core function all pipelines delegate to |
| Test suites | [tests/functional/](../../tests/functional/), [tests/system/](../../tests/system/), [tests/upgrade_sgw/](../../tests/upgrade_sgw/) | Source of `@pytest.mark.min_*` requirements |
| AWS orchestrator | [../../environment/aws/start_backend.py](../../environment/aws/start_backend.py) | Called by `setup_test()` |
| Topology schema | [../../environment/aws/topology_setup/topology_schema.json](../../environment/aws/topology_setup/topology_schema.json) | Validates topology JSON |
