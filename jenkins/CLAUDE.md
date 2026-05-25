# CLAUDE.md — CI/CD Pipelines (jenkins/)

## What This Is

This directory contains all Jenkins CI/CD pipelines for building test servers, provisioning
AWS environments, and running tests across all supported platforms. It also includes the
Jenkins server's own Docker setup.

## Directory Structure

```
jenkins/
├── pipelines/
│   ├── shared/                     # Shared scripts used by ALL pipelines
│   │   ├── setup_test.py           # setup_test() and setup_test_multi() — core setup logic
│   │   ├── config.sh               # Bash utilities: move_artifacts, find_dir, print_box, path exports
│   │   └── config.psm1             # PowerShell equivalent of config.sh
│   │
│   ├── prebuild/                   # Test server prebuild pipeline
│   │   └── Jenkinsfile             # Build + upload test server artifacts to latestbuilds
│   │
│   ├── dev_e2e/                    # Developer E2E test pipelines (one per platform)
│   │   ├── main/                   #   Main pipeline (latest_sgw_url.sh, latest_successful_build.sh)
│   │   ├── android/                #   Android: Jenkinsfile, setup_test.py, config_android.json, topology_single_device.json
│   │   ├── c/                      #   C: Jenkinsfile, setup_test.py, config.json, topologies/
│   │   ├── dotnet/                 #   .NET: Jenkinsfile, setup_test.py, config_aws.json, topologies/
│   │   ├── ios/                    #   iOS: Jenkinsfile, setup_test.py, config.json, topology_single_device.json
│   │   ├── java/                   #   Java: desktop/ and webservice/ sub-pipelines
│   │   ├── javascript/             #   JavaScript: Jenkinsfile, setup_test.py, config.json, topology_single_host.json
│   │   └── multipeer_functional/   #   Multi-platform multipeer: setup_test.py, topology.json
│   │
│   └── QE/                         # QA test pipelines (one per platform + special pipelines)
│       ├── android/                #   Android QE
│       ├── c/                      #   C QE
│       ├── dotnet/                 #   .NET QE
│       ├── ios/                    #   iOS QE
│       ├── java/                   #   Java QE (desktop/ + webservice/)
│       ├── sgw/                    #   SGW-focused QE tests (no specific platform)
│       ├── upg-sgw/                #   SGW upgrade tests (iterates SGW versions)
│       ├── es/                     #   Edge Server QE tests
│       └── multiplatform/          #   Multi-platform QE tests
│
└── docker/                         # Jenkins server Docker setup
    ├── docker-compose.yml          # Jenkins controller + agent
    ├── agent/                      # Jenkins agent Dockerfile
    └── nginx/                      # Nginx reverse proxy
```

## The `setup_test.py` Pattern (⚠️ MOST REPETITIVE CODE IN THE REPO)

Every `jenkins/pipelines/{dev_e2e,QE}/{platform}/setup_test.py` is nearly identical.
They all do one thing: call the shared `setup_test()` with platform-specific arguments.

### Template (what they ALL look like):
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
        cbl_version,
        sgw_version,
        SCRIPT_DIR / "TOPOLOGY_FILE",    # ← varies per platform
        SCRIPT_DIR / "CONFIG_FILE",       # ← varies per platform
        "PLATFORM_TAG",                   # ← varies per platform
        setup_dir="SUITE",                # ← "dev_e2e" (default) or "QE"
    )

if __name__ == "__main__":
    cli_entry()
```

### What Varies Per Platform

| Platform | `topology_file` | `config_file` | `platform_tag` | Extra args |
|----------|-----------------|---------------|-----------------|------------|
| android (dev_e2e) | `topology_single_device.json` | `config_android.json` | `jak_android` | — |
| ios (dev_e2e) | `topology_single_device.json` | `config.json` | `swift_ios` | — |
| c (dev_e2e) | `topologies/topology_single_{platform}.json` | `config.json` | `c_{platform}` | extra `platform` arg |
| dotnet (dev_e2e) | `topologies/topology_single_{platform}.json` | `config_aws.json` | `dotnet_{platform}` | extra `platform` + `cbs_version` args |
| javascript (dev_e2e) | `topology_single_host.json` | `config.json` | `js` | — |
| sgw (QE) | `topology.json` | `config.json` | `sgw` | `setup_dir="QE"` |
| upg-sgw (QE) | `topology.json` | `config.json` | `upg-sgw` | `setup_dir="QE"` |
| es (QE) | custom `setup_test.py` | `config.json` | `es` | **different pattern** — uses `generate_topology()` instead of shared `setup_test()` |

### Notable Exception: Edge Server (`QE/es/setup_test.py`)
This one does NOT use the shared `setup_test()`. It has its own `generate_topology()` function
and calls `start_backend()` directly. It handles ES-specific topology generation with
`--sgw-version` and `--cbs-version` options.

### Notable Exception: `multipeer_functional/setup_test.py`
Uses `setup_test_multi()` (not `setup_test()`) with a per-platform version map and custom
topology/config for multi-device mesh testing.

## The Shared Setup Logic (`shared/setup_test.py`)

### `setup_test(cbl_version, sgw_version, topology_file_in, config_file_in, topology_tag, couchbase_version, setup_dir)`
1. Creates a version map with `cbl_version` for all platforms
2. Delegates to `setup_test_multi()`

### `setup_test_multi(cbl_version_map, sgw_version, topology_file_in, config_file_in, topology_tag, ...)`
1. Reads the platform's topology JSON template
2. Rewrites `$schema` and `include` paths for the destination directory
3. Sets `defaults.cbs.version` and `defaults.sgw.version` from resolved versions
4. Sets `tag` and per-test-server `cbl_version`
5. Writes final topology to `environment/aws/topology_setup/topology.json`
6. Downloads `cbbackupmgr` tool for the CBS version
7. Creates `TopologyConfig` and calls `start_backend()` (the AWS orchestrator)

### Helper: `ts_to_topology(ts_platform)` — platform name mapping
```
swift_*   → ios
jak_android → android
jak_*     → java
dotnet_*  → dotnet
c_*       → c
```

## The Shell Script Pattern (`test.sh` / `run_test.sh`)

Every platform has a test runner script that follows this pattern:
```bash
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh     # Sets all path vars

# Setup backend
pushd $AWS_ENVIRONMENT_DIR > /dev/null
uv run $SCRIPT_DIR/setup_test.py $CBL_VERSION $SGW_VERSION
popd > /dev/null

# Run tests
pushd $DEV_E2E_TESTS_DIR > /dev/null        # or $QE_TESTS_DIR
uv run pytest -v --no-header --config config.json [-m MARKER]
popd > /dev/null
```

### Notable: `QE/upg-sgw/test.sh`
The SGW upgrade test script is unique — it:
1. Sets up with the first SGW version
2. Runs `upg_sgw` tests
3. Loops through remaining SGW versions: destroys SGW → re-provisions with new version → runs tests again

## Shell Utilities (`shared/config.sh`)

Defines these path constants (used by every `test.sh` and `teardown.sh`):
```bash
PIPELINES_DIR       # jenkins/pipelines/
TESTS_DIR           # tests/
ENVIRONMENT_DIR     # environment/
TEST_SERVER_DIR     # servers/
SHARED_PIPELINES_DIR    # jenkins/pipelines/shared/
DEV_E2E_PIPELINES_DIR  # jenkins/pipelines/dev_e2e/
DEV_E2E_TESTS_DIR      # tests/dev_e2e/
QE_TESTS_DIR            # tests/QE/
QE_PIPELINES_DIR        # jenkins/pipelines/QE/
AWS_ENVIRONMENT_DIR     # environment/aws/
```

Functions: `move_artifacts()`, `find_dir()`, `print_box()`

## Jenkinsfile Pattern

Every Jenkinsfile follows this structure:
```groovy
pipeline {
    agent none
    parameters {
        string(name: 'CBL_VERSION', ...)
        string(name: 'SGW_VERSION', ...)
    }
    stages {
        stage('Init') { ... }
        stage('Prebuild Servers') {
            // Calls prebuild-test-server job
            build job: 'prebuild-test-server', parameters: [...]
        }
        stage('Run Test') {
            agent { label 'AGENT_LABEL' }
            steps {
                sh "jenkins/pipelines/{suite}/{platform}/test.sh ..."
            }
            post {
                always {
                    sh "jenkins/pipelines/{suite}/{platform}/teardown.sh"
                    archiveArtifacts artifacts: 'tests/{suite}/**/*', ...
                }
            }
        }
    }
}
```

## Commands
```bash
# Nothing to run locally — Jenkins pipelines are triggered via Jenkins UI
# For local testing, the scripts can be invoked directly:

# Example: run iOS dev_e2e setup
cd environment/aws
uv run ../jenkins/pipelines/dev_e2e/ios/setup_test.py 4.0.0 4.0.0

# Example: source shared config
source jenkins/pipelines/shared/config.sh
```

## Rules
- **All `setup_test.py` files must add repo root to `sys.path`** — `sys.path.append(str(SCRIPT_DIR.parents[3]))`
- **Use `click`** for CLI argument parsing in all Python scripts
- **Use `setup_dir="QE"`** for QE pipelines (default is `"dev_e2e"`)
- **Topology and config files are templates** — committed to repo; final versions are generated
- **Always call `move_artifacts`** in teardown scripts (defined in `shared/config.sh`)
- **Teardown must run even on failure** — Jenkinsfile uses `post { always { ... } }`
- **Never commit generated files**: `config.json` in test dirs, `topology.json` in `topology_setup/`
- **Python 3.10+**: use `X | Y`, never `Union[X, Y]` or `Optional[X]`
- **⚠️ DO NOT create markdown documentation files** for pipeline changes. Markdown files are for AI understanding only. The actual pipeline code is self-documenting via shared scripts and comments.

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| AWS orchestrator | `environment/aws/start_backend.py` | Called by `setup_test()` to provision infra |
| AWS teardown | `environment/aws/stop_backend.py` | Called by `teardown.sh` or upgrade scripts |
| Shared setup logic | `jenkins/pipelines/shared/setup_test.py` | Core function all pipelines delegate to |
| Test suites | `tests/dev_e2e/`, `tests/QE/` | What the pipelines ultimately run |
| Test server source | `servers/` | Built by prebuild pipeline |
| Topology schema | `environment/aws/topology_setup/topology_schema.json` | Validates topology JSON |
| Config schema | `testserver.schema.json` (remote) | Validates generated config JSON |

