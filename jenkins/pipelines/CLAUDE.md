# CLAUDE.md — Pipeline Structure (jenkins/pipelines/)

## What This Is

This directory contains all Jenkins pipeline definitions organized by test suite type and platform.
It provides a structured approach to continuous integration across the Couchbase Lite System Test
Harness, with shared scripts, per-platform test runners, and specialized test pipelines.

## Directory Organization

```
pipelines/
├── shared/                          # Shared utilities used by ALL pipelines
│   ├── setup_test.py                # Core setup logic: setup_test() and setup_test_multi()
│   ├── config.sh                    # Bash path and utility functions
│   └── config.psm1                  # PowerShell equivalent of config.sh
│
├── prebuild/                        # Test server artifact prebuild pipeline
│   └── Jenkinsfile                  # Build matrix for all platform test servers
│
├── dev_e2e/                         # Developer E2E test pipelines (per-platform)
│   ├── android/                     # Android dev_e2e pipeline
│   ├── c/                           # C platform dev_e2e pipeline (with multi-platform topologies)
│   ├── dotnet/                      # .NET platform dev_e2e pipeline
│   ├── ios/                         # iOS dev_e2e pipeline
│   ├── java/                        # Java dev_e2e (desktop/ and webservice/)
│   ├── javascript/                  # JavaScript dev_e2e pipeline
│   └── multipeer_functional/        # Multi-platform multipeer functional tests
│
└── QE/                              # QA test pipelines (per-platform + special)
    ├── android/                     # Android QA pipeline
    ├── c/                           # C platform QA pipeline
    ├── dotnet/                      # .NET platform QA pipeline
    ├── ios/                         # iOS QA pipeline
    ├── java/                        # Java QA (desktop/ and webservice/)
    ├── sgw/                         # SGW-specific QA tests (no CBL platform)
    ├── upg-sgw/                     # SGW upgrade tests with multi-node clusters
    ├── es/                          # Edge Server QA tests (uses custom setup)
    └── multiplatform/               # Multi-platform QA tests
```

## Platform Pipeline Structure

Every platform directory (dev_e2e or QE) follows this consistent structure:

```
{platform}/
├── Jenkinsfile                      # Pipeline definition (Groovy)
├── setup_test.py                    # CLI to invoke shared setup_test() with platform args
├── config*.json                     # TDK config template(s) for the platform
├── topology*.json                   # Topology template(s) with resource requirements
├── test.sh / run_test.sh / run_test.ps1   # Test execution script
├── teardown.sh / teardown.ps1       # Environment cleanup script
└── (optional) — platform-specific extras
```

## Key Concepts

### Topology Files as Contracts

Topology JSON files define the infrastructure contract that **must match the test requirements**:

- Each `cluster` entry = 1 CBS instance
- Each `sync_gateways` entry = 1 SGW instance  
- Each `test_servers` entry = 1 test server instance

**Critical Rule:** The topology file MUST provision enough resources to satisfy ALL `@pytest.mark.min_*` 
decorators in the test suite.

**Example:**
```python
@pytest.mark.min_sync_gateways(2)      # Test requires 2 SGW nodes
@pytest.mark.min_couchbase_servers(2)  # Test requires 2 CBS instances
class TestMyTest:
    pass
```

Must be paired with:
```json
{
    "clusters": [{"server_count": 1}, {"server_count": 1}],    // 2 CBS clusters
    "sync_gateways": [{"cluster": 0}, {"cluster": 1}]          // 2 SGW nodes
}
```

### Setup Pattern

All `setup_test.py` files delegate to shared `setup_test()` or `setup_test_multi()`:

1. Parse topology JSON template
2. Resolve CBL/SGW/CBS versions
3. Validate topology against resource availability
4. Rewrite paths and version placeholders
5. Write final topology to `environment/aws/topology_setup/topology.json`
6. Call `start_backend.py` to provision infrastructure

### Special Cases

#### SGW Upgrade (upg-sgw/)
Unique pipeline that iterates through SGW versions:
1. Initial setup with first version
2. Run upgrade tests
3. Destroy SGW instances
4. Re-provision with next version
5. Run tests again
6. Repeat for all versions

**Topology requirement:** Must support multi-node SGW clusters for testing consistency.

#### Edge Server (es/)
Custom `setup_test.py` with `generate_topology()` function instead of using shared `setup_test()`.
Handles ES-specific topology generation with `--sgw-version` and `--cbs-version` CLI options.

#### Multi-Platform (multiplatform/)
Uses `setup_test_multi()` with per-platform version maps instead of single CBL version.
Tests cross-platform mesh scenarios (multipeer replication).

## Shared Scripts

### `shared/setup_test.py`

**`setup_test(cbl_version, sgw_version, topology_file_in, config_file_in, topology_tag, couchbase_version, setup_dir)`**
- Creates a version map with `cbl_version` for all platforms
- Delegates to `setup_test_multi()`

**`setup_test_multi(cbl_version_map, sgw_version, topology_file_in, config_file_in, topology_tag, ...)`**
- Reads topology template from the platform directory
- Resolves versions via proget API
- Validates resource counts
- Sets `defaults.cbs.version`, `defaults.sgw.version`, per-platform `cbl_version`
- Writes final topology to `environment/aws/topology_setup/topology.json`
- Downloads `cbbackupmgr` tool
- Creates `TopologyConfig` and calls `start_backend()`

### `shared/config.sh` & `config.psm1`

Path constants and utility functions used by all `test.sh` and `teardown.sh` scripts:
- `PIPELINES_DIR`, `TESTS_DIR`, `ENVIRONMENT_DIR`, `TEST_SERVER_DIR`
- `move_artifacts()` — copy test logs and artifacts
- `find_dir()` — locate directories by name
- `print_box()` — formatted output

## Important Rules

### Topology-Test Synchronization

- **CRITICAL:** Topology file resource counts MUST match test `@pytest.mark.min_*` decorators
- **FAIL:** If topology provisions fewer resources than tests require, tests will hang waiting for unavailable instances
- **AUDIT:** When adding new test requirements (e.g., 3 SGW nodes), update topology file first

### Template Placeholders

Topology and config files use templates with `{{placeholder}}` syntax:
- `{{version}}` — single CBL version (dev_e2e)
- `{{cbl_version}}` — single platform's CBL version
- `{{jak_android}}`, `{{jak_desktop}}`, `{{swift_ios}}`, etc. — per-platform versions (multiplatform)
- `{{cbs_version}}` — CBS version (some platforms)

All placeholders are resolved by `setup_test.py` before infrastructure provisioning.

### File Organization Patterns

1. **Single topology file** (`topology.json`) — most pipelines (simple infrastructure)
2. **Multiple topology files** (`topologies/topology_single_*.json`) — C and .NET platforms (multi-platform support)
3. **Custom topology generation** (`es/`) — Edge Server pipeline (programmatic topology)

## Commands

```bash
# Run a dev_e2e pipeline (invoked by Jenkins)
cd environment/aws
uv run ../jenkins/pipelines/dev_e2e/ios/setup_test.py 4.0.0 4.0.0

# Run a QE pipeline
uv run ../jenkins/pipelines/QE/upg-sgw/setup_test.py 4.0.0 4.0.0

# Teardown infrastructure
cd jenkins/pipelines/QE/upg-sgw
./teardown.sh
```

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| Test framework | `client/src/cbltest/` | Consumed by tests that pipelines run |
| Test suites | `tests/dev_e2e/`, `tests/QE/` | What pipelines ultimately execute |
| Test specifications | `spec/tests/dev_e2e/`, `spec/tests/QE/` | Define expected test behavior |
| Topology schema | `environment/aws/topology_setup/topology_schema.json` | Validates topology JSON files |
| AWS orchestrator | `environment/aws/start_backend.py` | Invoked by setup_test.py to provision infra |
| Test servers | `servers/` | Built by prebuild pipeline, deployed by topology setup |
| CI/CD root | `jenkins/CLAUDE.md` | Parent documentation for entire jenkins/ directory |

