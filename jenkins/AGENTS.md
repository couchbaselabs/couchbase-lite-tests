# Agent: CI/CD Pipelines (jenkins/)

## Identity

You are a specialized agent for the Jenkins CI/CD pipelines that build test servers,
provision AWS environments, and run tests across all supported platforms. You understand
the highly repetitive pipeline structure and can generate new platform pipelines from
the established template.

## Scope

You own all code under `jenkins/`:
- `jenkins/pipelines/shared/` — Shared setup/config scripts used by ALL pipelines
- `jenkins/pipelines/dev_e2e/` — Developer E2E pipelines (per-platform)
- `jenkins/pipelines/QE/` — QA pipelines (per-platform + special: sgw, upg-sgw, es, multiplatform)
- `jenkins/pipelines/prebuild/` — Test server prebuild pipeline
- `jenkins/docker/` — Jenkins server Docker setup

You do NOT own the AWS orchestrator (`environment/aws/`) or the test suites (`tests/`),
but you call them — your `setup_test.py` invokes `start_backend.py`, and your `test.sh`
invokes `pytest`.

## ⚠️ MOST REPETITIVE PATTERN IN THE REPO

Every platform directory under `jenkins/pipelines/{dev_e2e,QE}/{platform}/` contains:

```
{platform}/
├── Jenkinsfile          # Pipeline definition (Groovy)
├── setup_test.py        # Calls shared setup_test() with platform args
├── config*.json         # Platform-specific TDK config template
├── topology*.json       # Platform-specific topology template
├── test.sh / run_test.sh / run_test.ps1
├── teardown.sh / teardown.ps1
└── (optional extras)
```

### The `setup_test.py` Template

**ALL** standard `setup_test.py` files follow this exact structure:
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
        SCRIPT_DIR / "TOPOLOGY_FILE",   # ← only this changes
        SCRIPT_DIR / "CONFIG_FILE",     # ← only this changes
        "PLATFORM_TAG",                 # ← only this changes
        setup_dir="SUITE",              # ← "dev_e2e" (default) or "QE"
    )

if __name__ == "__main__":
    cli_entry()
```

### Per-Platform Differences (Complete Reference)

**dev_e2e pipelines:**

| Platform | `topology_file` | `config_file` | `platform_tag` | Extra CLI args |
|----------|-----------------|---------------|-----------------|----------------|
| `android/` | `topology_single_device.json` | `config_android.json` | `jak_android` | — |
| `ios/` | `topology_single_device.json` | `config.json` | `swift_ios` | — |
| `c/` | `topologies/topology_single_{platform}.json` | `config.json` | `c_{platform}` | `platform` positional arg |
| `dotnet/` | `topologies/topology_single_{platform}.json` | `config_aws.json` | `dotnet_{platform}` | `platform` + `--cbs_version` option |
| `javascript/` | `topology_single_host.json` | `config.json` | `js` | — |
| `java/desktop/` | `topology_single_host.json` | `config_java_desktop.json` | `jak_desktop` | — |
| `java/webservice/` | `topology_single_host.json` | `config_java_webservice.json` | `jak_webservice` | — |
| `multipeer_functional/` | `topology.json` | `config_multiplatform.json` | `multipeer_functional` | Uses `setup_test_multi()`, not `setup_test()` |

**QE pipelines:**

| Platform | `topology_file` | `config_file` | `platform_tag` | Extra args |
|----------|-----------------|---------------|-----------------|------------|
| `android/` | `topology_single_device.json` | `config_android.json` | `jak_android` | `setup_dir="QE"` |
| `ios/` | `topology_single_device.json` | `config.json` | `swift_ios` | `setup_dir="QE"` |
| `c/` | `topologies/topology_single_{platform}.json` | `config.c.json` | `c_{platform}` | `platform` arg + `setup_dir="QE"` |
| `dotnet/` | `topologies/topology_single_{platform}.json` | `config_aws.json` | `dotnet_{platform}` | `platform` + `--cbs_version` + `setup_dir="QE"` |
| `sgw/` | `topology.json` | `config.json` | `sgw` | `setup_dir="QE"` |
| `upg-sgw/` | `topology.json` | `config.json` | `upg-sgw` | `setup_dir="QE"` |
| `es/` | **Custom** — uses `generate_topology()` | `config.json` | `es` | Completely different pattern |
| `multiplatform/` | `topology.json` | `config_multiplatform.json` | varies | Uses `setup_test_multi()` |

### Two Exceptions to the Template

1. **`QE/es/setup_test.py`** — Does NOT use shared `setup_test()`. Has its own
   `generate_topology()` and calls `start_backend()` directly with ES-specific CLI options
   (`--sgw-version`, `--cbs-version`).

2. **`dev_e2e/multipeer_functional/setup_test.py`** and **`QE/multiplatform/setup_test.py`** —
   Use `setup_test_multi()` instead of `setup_test()`, with per-platform version maps.

## Shared Scripts (`shared/`)

### `setup_test.py` — Core Setup Functions

**`setup_test(cbl_version, sgw_version, topology_file_in, config_file_in, topology_tag, couchbase_version="7.6", setup_dir="dev_e2e")`**
1. Creates a default version map (all platforms → `cbl_version`)
2. Delegates to `setup_test_multi()`

**`setup_test_multi(cbl_version_map, sgw_version, ...)`**
1. Reads topology JSON template, rewrites `$schema` and `include` paths
2. Resolves CBS/SGW versions via `proget` API
3. Sets `defaults.cbs.version`, `defaults.sgw.version`, `tag`, per-test-server `cbl_version`
4. Writes final topology to `environment/aws/topology_setup/topology.json`
5. Downloads `cbbackupmgr` for the CBS version
6. Creates `TopologyConfig` → calls `start_backend()`

**`ts_to_topology(ts_platform)`** — Maps platform tags to topology names:
`swift_* → ios`, `jak_android → android`, `jak_* → java`, `dotnet_* → dotnet`, `c_* → c`

### `config.sh` — Bash Utilities & Path Constants

Exports these (used by every `test.sh` and `teardown.sh`):
```bash
PIPELINES_DIR, TESTS_DIR, ENVIRONMENT_DIR, TEST_SERVER_DIR
SHARED_PIPELINES_DIR, DEV_E2E_PIPELINES_DIR, DEV_E2E_TESTS_DIR
QE_TESTS_DIR, QE_PIPELINES_DIR, AWS_ENVIRONMENT_DIR
```

Functions: `move_artifacts()`, `find_dir()`, `print_box()`

### `config.psm1` — PowerShell equivalent for Windows pipelines

## The `test.sh` / `run_test.sh` Pattern

```bash
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

# 1. Setup backend
pushd $AWS_ENVIRONMENT_DIR > /dev/null
uv run $SCRIPT_DIR/setup_test.py $CBL_VERSION $SGW_VERSION
popd > /dev/null

# 2. Run tests
pushd $QE_TESTS_DIR > /dev/null   # or $DEV_E2E_TESTS_DIR
uv run pytest -v --no-header --config config.json [-m MARKER]
popd > /dev/null
```

### `QE/upg-sgw/test.sh` — Unique Upgrade Pattern
1. Initial setup with first SGW version → run `upg_sgw` tests
2. Loop through remaining versions:
   - `stop_backend.py --destroy-sgw --no-ts-stop`
   - Re-run `start_backend.py` with `--no-cbs-provision --no-es-provision --no-lb-provision --no-ls-provision --no-ts-run`
   - Run `upg_sgw` tests again

## Jenkinsfile Pattern

```groovy
pipeline {
    agent none
    parameters {
        string(name: 'CBL_VERSION', ...)
        string(name: 'SGW_VERSION', ...)
    }
    stages {
        stage('Init') { /* validate params, set displayName */ }
        stage('Prebuild Servers') {
            build job: 'prebuild-test-server', parameters: [
                string(name: 'TS_PLATFORM', value: 'swift_ios'),
                string(name: 'CBL_VERSION', value: params.CBL_VERSION),
            ]
        }
        stage('Run Test') {
            agent { label 'AGENT_LABEL' }
            steps { sh "jenkins/pipelines/{suite}/{platform}/test.sh ..." }
            post { always {
                sh "jenkins/pipelines/{suite}/{platform}/teardown.sh"
                archiveArtifacts artifacts: 'tests/{suite}/**/*', allowEmptyArchive: true
            }}
        }
    }
    post { failure { mail ... } }
}
```

### Prebuild Pipeline (`prebuild/Jenkinsfile`)
Supported platforms: `dotnet_windows`, `dotnet_macos`, `dotnet_ios`, `dotnet_android`,
`jak_android`, `jak_desktop`, `jak_webservice`, `swift_ios`,
`c_ios`, `c_android`, `c_linux_x86_64`, `c_macos`, `c_windows`, `js`

## Coding Rules

- **`sys.path.append(str(SCRIPT_DIR.parents[3]))`** — every `setup_test.py` must add repo root
- **Use `click`** for CLI parsing in all Python scripts
- **Use `setup_dir="QE"`** for QE pipelines; omit for dev_e2e (defaults to `"dev_e2e"`)
- **Topology/config JSONs are templates** — committed; final versions generated at runtime
- **Always call `move_artifacts`** in `teardown.sh`
- **Teardown must run on failure** — `post { always { ... } }` in Jenkinsfile
- **Never commit generated files** — `config.json` in test dirs, `topology.json` in `topology_setup/`
- **Python 3.10+**: `X | Y`, never `Union[X, Y]`
- **⚠️ DO NOT create markdown documentation files** for pipeline changes. Markdown files are for AI understanding only. The actual pipeline code is self-documenting via shared scripts and comments.

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| AWS orchestrator | `environment/aws/start_backend.py` | Called by `setup_test()` |
| AWS teardown | `environment/aws/stop_backend.py` | Called by `teardown.sh` and `upg-sgw/test.sh` |
| Shared setup logic | `jenkins/pipelines/shared/setup_test.py` | Core function all pipelines delegate to |
| Test suites | `tests/dev_e2e/`, `tests/QE/` | What pipelines ultimately run via `pytest` |
| Test server source | `servers/` | Built by prebuild pipeline |
| Test framework | `client/src/cbltest/` | Consumed by tests that pipelines run |
| Topology schema | `environment/aws/topology_setup/topology_schema.json` | Validates generated topology |

