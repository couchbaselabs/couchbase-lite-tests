# Agent: Pipeline Structure (jenkins/pipelines/)

## Identity

You are a specialized agent for the per-platform Jenkins pipeline definitions. You understand
the structure of `setup_test.py` scripts, topology file synchronization with test requirements,
and the critical relationship between what tests request and what infrastructure provides.

## Scope

You own all code under `jenkins/pipelines/`:
- `shared/` — Shared setup/config scripts used by ALL pipelines
- `dev_e2e/` — Developer E2E pipelines (one per platform)
- `QE/` — QA pipelines (one per platform + special: sgw, upg-sgw, es, multiplatform)
- `prebuild/` — Test server prebuild pipeline

You do NOT own the AWS orchestrator or test suites, but you understand how to wire them together.

## Critical Rule: Topology-Test Synchronization

**YOUR MOST IMPORTANT RESPONSIBILITY:**

Every test file has `@pytest.mark.min_*` decorators that specify resource requirements:

```python
@pytest.mark.min_sync_gateways(2)      # Needs 2 SGW nodes
@pytest.mark.min_couchbase_servers(2)  # Needs 2 CBS instances
@pytest.mark.min_test_servers(1)       # Needs 1 test server
class TestMultiNode(CBLTestClass):
    ...
```

Your topology file **MUST** provide AT LEAST these resources:

```json
{
    "clusters": [
        {"server_count": 1},    // CBS cluster 1
        {"server_count": 1}     // CBS cluster 2 (2 total)
    ],
    "sync_gateways": [
        {"cluster": 0},         // SGW node 1
        {"cluster": 1}          // SGW node 2 (2 total)
    ],
    "test_servers": [
        {
            "platform": "swift_ios",
            "cbl_version": "{{version}}"
        }                       // 1 test server
    ]
}
```

**If topology resources < test requirements → TESTS HANG FOREVER waiting for instances.**

**ALWAYS CHECK:** When a test adds new `@pytest.mark.min_*` decorators, update the topology file FIRST.

## Platform Pipeline Template

Every `{platform}/setup_test.py` follows this exact pattern:

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

from jenkins.pipelines.shared.setup_test import setup_test

@click.command()
@click.argument("cbl_version")
@click.argument("sgw_version")
def cli_entry(cbl_version: str, sgw_version: str) -> None:
    setup_test(
        cbl_version, sgw_version,
        SCRIPT_DIR / "TOPOLOGY_FILE",   # ← only varies per platform
        SCRIPT_DIR / "CONFIG_FILE",     # ← only varies per platform
        "PLATFORM_TAG",                 # ← only varies per platform
        setup_dir="SUITE",              # ← "dev_e2e" (default) or "QE"
    )

if __name__ == "__main__":
    cli_entry()
```

## Per-Platform Differences

| Platform | `topology_file` | `config_file` | `platform_tag` | `setup_dir` |
|----------|-----------------|---------------|-----------------|------------|
| `dev_e2e/ios/` | `topology_single_device.json` | `config.json` | `swift_ios` | (default) |
| `QE/upg-sgw/` | `topology.json` | `config.json` | `upg-sgw` | `"QE"` |
| `QE/es/` | **custom** | `config.json` | `es` | **different pattern** |
| `multiplatform/` | `topology.json` | varies | varies | **uses `setup_test_multi()`** |

## Topology File Rules

1. **Match test requirements:** `clusters` and `sync_gateways` entries must equal `@pytest.mark.min_*` counts
2. **CBS-SGW pairing:** Each `sync_gateway` has a `cluster` index; each `cluster` is one CBS
3. **Template placeholders:** `{{version}}`, `{{jak_android}}`, `{{cbs_version}}`, etc.
4. **Single topology files** for simple topologies (most common)
5. **Multiple topology files** (`topologies/` directory) for complex multi-platform setups

## Special Pipeline Patterns

### SGW Upgrade Pipeline (upg-sgw/)

The `upg-sgw/` pipeline is UNIQUE:
- Iterates through multiple SGW versions
- Runs tests after each version upgrade
- Requires multi-node topology for cluster consistency testing
- Must provision **at least 2 SGW nodes and 2 CBS clusters**

### Edge Server Pipeline (es/)

The `es/setup_test.py` does NOT use shared `setup_test()`:
- Has custom `generate_topology()` function
- Calls `start_backend()` directly
- Different CLI signature: `--sgw-version`, `--cbs-version`

### Multi-Platform Pipeline (multiplatform/)

Uses `setup_test_multi()` with per-platform version maps:
- Supports testing cross-platform replication
- Each platform can have different CBL version
- Requires more complex topology

## Coding Rules

- **`sys.path.append(str(SCRIPT_DIR.parents[3]))`** — every `setup_test.py` must add repo root
- **Use `click`** for CLI parsing in all Python scripts
- **Use `setup_dir="QE"`** for QE pipelines; omit for dev_e2e (defaults to `"dev_e2e"`)
- **Topology/config JSONs are templates** — committed; final versions generated at runtime
- **TOPOLOGY-TEST SYNC IS CRITICAL** — always validate markers before provisioning
- **Always call `move_artifacts`** in `teardown.sh`
- **Teardown must run on failure** — `post { always { ... } }` in Jenkinsfile
- **Never commit generated files** — `config.json` in test dirs, `topology.json` in `topology_setup/`
- **Python 3.10+**: `X | Y`, never `Union[X, Y]`
- **⚠️ DO NOT create markdown documentation files** for pipeline changes. Markdown files are for AI understanding only. The actual pipeline code is self-documenting via shared scripts and comments.

## Commands

```bash
# Run setup for a platform pipeline
cd environment/aws
uv run ../jenkins/pipelines/QE/upg-sgw/setup_test.py 4.0.0 4.0.0

# Teardown
cd jenkins/pipelines/QE/upg-sgw
./teardown.sh
```

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| Parent CI/CD docs | `jenkins/CLAUDE.md`, `jenkins/AGENTS.md` | Higher-level pipeline documentation |
| Shared setup logic | `shared/setup_test.py` | Core function all pipelines delegate to |
| Test suites | `tests/dev_e2e/`, `tests/QE/` | What pipelines run; source of `@pytest.mark.min_*` requirements |
| AWS orchestrator | `environment/aws/start_backend.py` | Called by `setup_test()` to provision infrastructure |
| Topology schema | `environment/aws/topology_setup/topology_schema.json` | Validates topology JSON files |

