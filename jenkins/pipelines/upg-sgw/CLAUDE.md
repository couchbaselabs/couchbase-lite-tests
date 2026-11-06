@AGENTS.md

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

#### Multi-Platform Pipeline (multiplatform/)

The `multiplatform/` pipeline (runs `tests/multiplatform`):
- **Cross-platform replication tests** — C, .NET, iOS, Java all syncing together
- Does not call the shared `setup_test()` — has its own inline topology-composition logic with per-platform version maps
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
# Run a platform pipeline's setup (platform pipelines live in ../functional/)
cd environment/aws
uv run ../jenkins/pipelines/functional/{platform}/setup_test.py 4.0.0 4.0.0

# Run SGW upgrade tests
uv run ../jenkins/pipelines/upg-sgw/setup_test.py 4.0.0 4.0.0

# Teardown infrastructure
cd jenkins/pipelines/functional/{platform}
./teardown.sh
```

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| Parent pipelines docs | `../CLAUDE.md`, `../AGENTS.md` | Higher-level pipeline guidance |
| Test suites | `../../../tests/functional/`, `../../../tests/system/`, `../../../tests/upgrade_sgw/` | Source of `@pytest.mark.min_*` requirements |
| Test specifications | `../../../spec/tests/QE/` | Define expected behavior for QE tests |
| Shared setup logic | `../shared/setup_test.py` | Core function all QE pipelines delegate to |
| AWS orchestrator | `../../../environment/aws/start_backend.py` | Called to provision infrastructure |

