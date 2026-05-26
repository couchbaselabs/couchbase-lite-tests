# CLAUDE.md — dev_e2e Test Pipelines (jenkins/pipelines/dev_e2e/)

## What This Is

This directory contains the Developer End-to-End (dev_e2e) test pipelines for the Couchbase Lite
System Test Harness. These pipelines focus on core replication and feature coverage during CBL
releases, with tests that verify basic functionality across all supported platforms.

## Directory Structure

```
dev_e2e/
├── android/                         # Android dev_e2e pipeline
├── c/                               # C platform dev_e2e pipeline (with multi-platform topologies)
├── dotnet/                          # .NET platform dev_e2e pipeline
├── ios/                             # iOS dev_e2e pipeline
├── java/                            # Java dev_e2e (desktop/ and webservice/)
├── javascript/                      # JavaScript dev_e2e pipeline
└── multipeer_functional/            # Multi-platform multipeer functional tests
```

## Pipeline Types

### Standard Platform Pipelines

Most dev_e2e pipelines follow the standard structure with `setup_test.py` delegating to shared `setup_test()`:
- `android/`, `c/`, `dotnet/`, `ios/`, `java/`, `javascript/`

Each has:
- `Jenkinsfile` — Pipeline definition
- `setup_test.py` — Calls `setup_test()` with platform-specific args
- `topology*.json` — Infrastructure template(s)
- `config*.json` — TDK config template(s)
- `test.sh` or `run_test.sh` — Runs tests via `pytest`
- `teardown.sh` — Cleanup script

### Special Pipelines

#### Multi-Platform Multipeer Pipeline (multipeer_functional/)

The `multipeer_functional/` pipeline:
- **Cross-platform mesh replication** — Multiple platforms (C, .NET, iOS, Java, JS) syncing together
- Uses `setup_test_multi()` with per-platform version maps
- Each platform can have different CBL version
- Tests peer-to-peer replication across multiple devices
- Complex topology with multiple test servers on different platforms

## Topology File Rules

1. **Match test requirements:** `clusters` and `sync_gateways` entries must satisfy `@pytest.mark.min_*` counts
2. **CBS-SGW pairing:** Each `sync_gateway` has a `cluster` index; each `cluster` is one CBS
3. **Template placeholders:** `{{version}}`, `{{jak_android}}`, `{{cbs_version}}`, etc.
4. **Single topology files** for simple topologies (most common)
5. **Multiple topology files** (`topologies/` directory) for complex multi-platform setups (C, .NET)

**Example (single SGW/CBS pair):**
```json
{
    "clusters": [{"server_count": 1}],
    "sync_gateways": [{"cluster": 0}],
    "test_servers": [{"platform": "swift_ios", "cbl_version": "{{version}}"}]
}
```

## Standard dev_e2e Pipeline Template

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
        SCRIPT_DIR / "topology.json",     # ← platform-specific topology
        SCRIPT_DIR / "config.json",       # ← platform-specific config
        "platform_tag",                   # ← e.g., "swift_ios", "jak_android"
        setup_dir="dev_e2e"               # ← or omit (dev_e2e is default)
    )

if __name__ == "__main__":
    cli_entry()
```

## Key Differences from QE

| Aspect | dev_e2e | QE |
|--------|---------|-----|
| Topology | Simple (usually 1 SGW, 1 CBS) | Complex (can be 2+ SGW, 2+ CBS) |
| Test scope | Core features, basic replication | Broader coverage, edge cases |
| Cleanup | Tests run during release | Auto-cleanup via conftest fixture |
| Multi-node | Generally not tested | Yes (e.g., upg-sgw) |

## Commands

```bash
# Run a dev_e2e pipeline
cd environment/aws
uv run ../jenkins/pipelines/dev_e2e/ios/setup_test.py 4.0.0 4.0.0

# Teardown infrastructure
cd jenkins/pipelines/dev_e2e/ios
./teardown.sh
```

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| Parent pipelines docs | `../CLAUDE.md`, `../AGENTS.md` | Higher-level pipeline documentation |
| dev_e2e test suites | `../../../tests/dev_e2e/` | Source of requirements |
| Test specifications | `../../../spec/tests/dev_e2e/` | Define expected behavior for dev_e2e tests |
| Shared setup logic | `../shared/setup_test.py` | Core function all pipelines delegate to |
| AWS orchestrator | `../../../environment/aws/start_backend.py` | Called to provision infrastructure |

