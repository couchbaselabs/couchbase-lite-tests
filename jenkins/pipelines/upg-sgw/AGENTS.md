# Agent: SGW Upgrade and Multi-Platform Pipelines (jenkins/pipelines/upg-sgw/, jenkins/pipelines/multiplatform/)

## Identity

You maintain the pipelines whose topologies go beyond one test server and one Sync Gateway:
SGW upgrade scenarios (`upg-sgw/`) and multi-platform tests (`../multiplatform/`). You focus on
ensuring topology files match test requirements and on multi-node cluster configurations.

## Scope

You own:
- `jenkins/pipelines/upg-sgw/` — SGW upgrade (`Jenkinsfile`) and rolling upgrade (`Jenkinsfile_rolling`), running `tests/upgrade_sgw`
- `jenkins/pipelines/multiplatform/` — runs `tests/multiplatform` with several test servers (on one or more platforms) in one topology

Platform pipelines live in `../functional/`; the daily triggers live in `../main/` (`cbl/`, `sgw/`).

You do NOT own the test code (`tests/functional/`, `tests/system/`, `tests/upgrade_sgw/`), but you are responsible for provisioning
the infrastructure that those tests require.

## Your Most Critical Responsibility: Topology-Test Synchronization

### The Rule

Every QE test file has `@pytest.mark.min_*` decorators that declare infrastructure requirements:

```python
@pytest.mark.min_sync_gateways(2)  # Test REQUIRES 2 SGW nodes
@pytest.mark.min_couchbase_servers(2)  # Test REQUIRES 2 CBS instances
@pytest.mark.min_test_servers(1)  # Test REQUIRES 1 test server
class TestMultiNode(CBLTestClass): ...
```

**YOUR JOB:** Ensure the corresponding `topology.json` provides **AT LEAST** these resources.

### The Failure Mode

If topology provisions FEWER resources than tests require:
- Tests hang forever waiting for unavailable instances
- Infrastructure costs climb (paying for idle instances)
- CI/CD pipelines fail with timeout errors

### The Audit Process

When ANY test is modified to add new `@pytest.mark.min_*` decorators:

1. **FIRST:** Update the topology.json file
2. **THEN:** Update the test code
3. **VERIFY:** `pytest.mark.min_*` count ≤ topology count

### Example: SGW Upgrade (upg-sgw/)

**Test requirements:**
```python
@pytest.mark.min_sync_gateways(2)      # 2 SGW nodes needed
@pytest.mark.min_couchbase_servers(2)  # 2 CBS instances needed
```

**Topology must provide:**
```json
{
    "clusters": [
        {"server_count": 1},           // CBS cluster 0
        {"server_count": 1}            // CBS cluster 1 (total: 2)
    ],
    "sync_gateways": [
        {"cluster": 0},                // SGW node 0 on cluster 0
        {"cluster": 1}                 // SGW node 1 on cluster 1 (total: 2)
    ]
}
```

## Standard QE Pipeline Template

```python
#!/usr/bin/env python3
import os, sys
from io import TextIOWrapper
from pathlib import Path
import click

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[3]))
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

from jenkins.pipelines.shared.setup_test import VersionType, setup_test


@click.command()
@click.argument("cbl_versions", type=VersionType())
@click.argument("sgw_versions", type=VersionType())
def cli_entry(cbl_versions: list[str], sgw_versions: list[str]) -> None:
    setup_test(
        cbl_versions,
        sgw_versions,
        SCRIPT_DIR / "topology.json",  # ← platform-specific topology
        SCRIPT_DIR / "config.json",  # ← platform-specific config
        "platform_tag",  # ← e.g., "swift_ios", "jak_android"
    )


if __name__ == "__main__":
    cli_entry()
```

## Special Cases

### SGW Upgrade Pipeline (upg-sgw/) — Most Critical

**Multi-Generation Topology:**
- 2 SGW nodes + 2 CBS clusters
- Nodes are paired: SGW[0] → CBS[0], SGW[1] → CBS[1]
- Allows cluster consistency testing across upgrades

**Test Pattern:**
1. Provision infrastructure with SGW version N
2. Run tests that verify upgrade works correctly
3. Destroy SGW (keep CBS)
4. Provision SGW version N+1
5. Repeat tests (verifying data persistence)

### Multi-Platform Pipeline (multiplatform/)

**Per-Platform Versions:**
- `setup_multiplatform.py` checks `PLATFORM_VERSIONS` against `topology.json` (every test server the agent can reach) and ProGet, then calls the shared `setup_test()` on just the test servers the entries use.
- Each platform can run different CBL version
- Topology supports multiple test servers

## Coding Rules

- **Topology MUST match test requirements** — non-negotiable
- **`setup_dir`** omitted (defaults to `"functional"`) except `upg-sgw`, which passes `"upgrade_sgw"`
- **Never hand-edit generated topology** — it's written at runtime by setup_test.py
- **Validate topology against schema** — `jsonschema` validates against `topology_schema.json`
- **Template placeholders** are resolved at runtime: `{{version}}`, `{{cbs_version}}`, etc.
- **Python 3.13+**: `X | Y`, never `Union[X, Y]`
- **⚠️ DO NOT create markdown documentation files** for changes. Markdown is for AI understanding only. The actual pipeline code is self-documenting via shared scripts and comments.

## Commands

```bash
# Validate topology against schema (from repo root)
jsonschema -i jenkins/pipelines/upg-sgw/topology.json \
  environment/aws/topology_setup/topology_schema.json

# Run QE pipeline (SGW upgrade)
cd environment/aws
uv run ../jenkins/pipelines/upg-sgw/setup_test.py 4.0.0 4.0.0

# Teardown
cd jenkins/pipelines/upg-sgw
./teardown.sh
```

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| Parent pipelines docs | `../CLAUDE.md`, `../AGENTS.md` | Higher-level pipeline documentation |
| Test suites | `../../../tests/functional/`, `../../../tests/system/`, `../../../tests/upgrade_sgw/` | Source of `@pytest.mark.min_*` requirements |
| Topology schema | `../../../environment/aws/topology_setup/topology_schema.json` | Validates topology JSON |
| Shared setup | `../shared/setup_test.py` | `setup_test()` function all QE pipelines use |
| AWS orchestrator | `../../../environment/aws/start_backend.py` | Called by setup_test() to provision infra |

