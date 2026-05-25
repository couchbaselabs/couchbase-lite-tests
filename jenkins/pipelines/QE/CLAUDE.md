# CLAUDE.md — QE Test Pipelines (jenkins/pipelines/QE/)

## What This Is

This directory contains the QA test pipelines for the Couchbase Lite System Test Harness. Unlike
`dev_e2e/` which focuses on core developer-facing features, the QE suite includes:
- Broader regression coverage
- Edge cases and failure scenarios
- Multi-node cluster testing
- SGW upgrade scenarios
- Edge Server functionality
- Multi-platform integration tests

## Directory Structure

```
QE/
├── android/                         # Android QA pipeline
├── c/                               # C platform QA pipeline
├── dotnet/                          # .NET platform QA pipeline
├── ios/                             # iOS QA pipeline
├── java/                            # Java QA (desktop/ + webservice/)
├── sgw/                             # SGW-specific QA tests (no CBL platform)
├── upg-sgw/                         # SGW upgrade tests with multi-node clusters
├── es/                              # Edge Server QA tests (custom setup)
└── multiplatform/                   # Multi-platform QA tests
```

## Pipeline Types

### Standard Platform Pipelines

Most QE pipelines follow the standard structure with `setup_test.py` delegating to shared `setup_test()`:
- `android/`, `c/`, `dotnet/`, `ios/`, `java/`

Each has:
- `Jenkinsfile` — Pipeline definition
- `setup_test.py` — Calls `setup_test()` with platform-specific args
- `topology*.json` — Infrastructure template(s)
- `config*.json` — TDK config template(s)
- `test.sh` — Runs tests via `pytest`
- `teardown.sh` — Cleanup script

### Special Pipelines

#### SGW Pipeline (sgw/)

The `sgw/` pipeline is unique:
- **No specific CBL platform** — tests SGW itself, not platform-specific CBL features
- Tests: user/role management, database replication, advanced SGW features
- Single SGW node, single CBS instance
- Topology: `topology.json`

#### SGW Upgrade Pipeline (upg-sgw/) — MOST CRITICAL

The `upg-sgw/` pipeline:
- **Iterates through multiple SGW versions** — runs tests after each upgrade
- **Multi-node cluster testing** — 2 SGW nodes + 2 CBS instances (for consistency)
- Tests data persistence and replication across version boundaries
- Unique flow: initial setup → run tests → destroy SGW → re-provision new version → repeat
- Topology: `topology.json` with 2 clusters and 2 sync_gateways

**Topology-Test Synchronization Requirement:**
```
Test markers:
  @pytest.mark.min_sync_gateways(2)         ← requires 2 SGW nodes
  @pytest.mark.min_couchbase_servers(2)     ← requires 2 CBS instances

Topology must provide:
  "clusters": [{"server_count": 1}, {"server_count": 1}]     // 2 CBS
  "sync_gateways": [{"cluster": 0}, {"cluster": 1}]          // 2 SGW
```

#### Edge Server Pipeline (es/)

The `es/` pipeline:
- **Custom `setup_test.py`** — NOT using shared `setup_test()`
- Has own `generate_topology()` function
- CLI: `--sgw-version`, `--cbs-version` (programmatic topology generation)
- Tests Edge Server-specific functionality

#### Multi-Platform Pipeline (multiplatform/)

The `multiplatform/` pipeline:
- **Cross-platform replication tests** — C, .NET, iOS, Java all syncing together
- Uses `setup_test_multi()` with per-platform version maps
- Single topology, multiple test servers
- Complex topology with multiple platforms and topologies

## Important Files

### upg-sgw/topology.json

**CRITICAL: This file must provision resources matching test requirements.**

Current (correct) structure:
```json
{
    "clusters": [
        {"server_count": 1},
        {"server_count": 1}
    ],
    "sync_gateways": [
        {"cluster": 0},
        {"cluster": 1}
    ]
}
```

**If you change test markers from `min_couchbase_servers(1)` to `(2)`, you MUST update this.**

## Commands

```bash
# Run QE pipeline for specific platform
cd environment/aws
uv run ../jenkins/pipelines/QE/{platform}/setup_test.py 4.0.0 4.0.0

# Run SGW upgrade tests
uv run ../jenkins/pipelines/QE/upg-sgw/setup_test.py 4.0.0 4.0.0

# Teardown infrastructure
cd jenkins/pipelines/QE/{platform}
./teardown.sh
```

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| Parent pipelines docs | `../CLAUDE.md`, `../AGENTS.md` | Higher-level pipeline guidance |
| QE test suites | `../../tests/QE/` | Source of `@pytest.mark.min_*` requirements |
| Test specifications | `../../spec/tests/QE/` | Define expected behavior for QE tests |
| Shared setup logic | `../shared/setup_test.py` | Core function all QE pipelines delegate to |
| AWS orchestrator | `../../environment/aws/start_backend.py` | Called to provision infrastructure |

