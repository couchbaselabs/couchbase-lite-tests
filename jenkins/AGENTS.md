# CI/CD Pipelines — `jenkins/`

All Jenkins pipelines for building test servers, provisioning AWS environments, and running tests across every platform. Also contains the Jenkins server's own Docker setup.

## Scope

You own everything under `jenkins/`:
- `jenkins/pipelines/shared/` — scripts used by **all** pipelines
- `jenkins/pipelines/dev_e2e/` — per-platform developer E2E pipelines
- `jenkins/pipelines/QE/` — per-platform QA pipelines + special pipelines (`sgw`, `upg-sgw`, `es`, `multiplatform`)
- `jenkins/pipelines/prebuild/` — test server prebuild pipeline
- `jenkins/docker/` — Jenkins controller + agent Docker setup

You do **not** own the AWS orchestrator (`environment/aws/`) or the test suites (`tests/`), but you call them: `setup_test.py` → `start_backend.py`; `test.sh` → `pytest`.

## Layout

```
jenkins/
├── pipelines/
│   ├── shared/                         # Used by ALL pipelines
│   │   ├── setup_test.py               # setup_test() — takes lists of CBL/SGW versions
│   │   ├── config.sh                   # Bash: move_artifacts, find_dir, print_box, path exports
│   │   └── config.psm1                 # PowerShell equivalent (Windows pipelines)
│   │
│   ├── prebuild/                       # Test server prebuild
│   │   └── Jenkinsfile                 # Builds + uploads artifacts to latestbuilds
│   │
│   ├── dev_e2e/                        # Developer E2E (per platform)
│   │   ├── main/                       #   latest_sgw_url.sh, latest_successful_build.sh
│   │   ├── android/                    #   Jenkinsfile + setup_test.py + config_android.json + topology_single_device.json
│   │   ├── c/                          #   Jenkinsfile + setup_test.py + config.json + topologies/
│   │   ├── dotnet/                     #   Jenkinsfile + setup_test.py + config_aws.json + topologies/
│   │   ├── ios/                        #   Jenkinsfile + setup_test.py + config.json + topology_single_device.json
│   │   ├── java/                       #   desktop/ + webservice/ sub-pipelines
│   │   ├── javascript/                 #   Jenkinsfile + setup_test.py + config.json + topology_single_host.json
│   │   └── multipeer_functional/       #   Multi-platform multipeer (per-platform version map → positional list)
│   │
│   └── QE/                             # QA (per platform + special)
│       ├── android/, c/, dotnet/, ios/, java/
│       ├── sgw/                        #   SGW-focused QE (no specific platform)
│       ├── upg-sgw/                    #   SGW upgrade (iterates versions)
│       ├── es/                         #   Edge Server (different pattern)
│       └── multiplatform/              #   Multi-platform QE
│
└── docker/                             # Jenkins server Docker setup
    ├── docker-compose.yml              # Controller + agent
    ├── agent/                          # Agent Dockerfile
    └── nginx/                          # Reverse proxy
```

## The `setup_test.py` Template ⚠️ MOST REPETITIVE PATTERN IN THE REPO

Every standard `setup_test.py` is nearly identical — it only varies in three string arguments.

```python
#!/usr/bin/env python3
import os, sys
from io import TextIOWrapper
from pathlib import Path
import click

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[3]))  # repo root on sys.path
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

from jenkins.pipelines.shared.setup_test import parse_versions, setup_test


@click.command()
@click.argument("cbl_version")
@click.argument("sgw_version")
def cli_entry(cbl_version: str, sgw_version: str) -> None:
    setup_test(
        parse_versions(cbl_version),
        parse_versions(sgw_version),
        SCRIPT_DIR / "TOPOLOGY_FILE",  # ← varies per platform
        SCRIPT_DIR / "CONFIG_FILE",  # ← varies per platform
        "PLATFORM_TAG",  # ← varies per platform
        setup_dir="SUITE",  # "dev_e2e" (default) or "QE"
    )


if __name__ == "__main__":
    cli_entry()
```

### dev_e2e per-platform arguments

| Platform | `topology_file` | `config_file` | `platform_tag` | Extra CLI args |
|---|---|---|---|---|
| `android/` | `topology_single_device.json` | `config_android.json` | `jak_android` | — |
| `ios/` | `topology_single_device.json` | `config.json` | `swift_ios` | — |
| `c/` | `topologies/topology_single_{platform}.json` | `config.json` | `c_{platform}` | `platform` positional |
| `dotnet/` | `topologies/topology_single_{platform}.json` | `config_aws.json` | `dotnet_{platform}` | `platform` + `--cbs_version` |
| `javascript/` | `topology_single_host.json` | `config.json` | `js` | — |
| `java/desktop/` | `topology_single_host.json` | `config_java_desktop.json` | `jak_desktop` | — |
| `java/webservice/` | `topology_single_host.json` | `config_java_webservice.json` | `jak_webservice` | — |
| `multipeer_functional/` | `topology.json` | `config_multiplatform.json` | `multipeer_functional` | Expands a per-platform version map into a positional `cbl_versions` list |

### QE per-platform arguments

| Platform | `topology_file` | `config_file` | `platform_tag` | Extra args |
|---|---|---|---|---|
| `android/` | `topology_single_device.json` | `config_android.json` | `jak_android` | `setup_dir="QE"` |
| `ios/` | `topology_single_device.json` | `config.json` | `swift_ios` | `setup_dir="QE"` |
| `c/` | `topologies/topology_single_{platform}.json` | `config.c.json` | `c_{platform}` | `platform` + `setup_dir="QE"` |
| `dotnet/` | `topologies/topology_single_{platform}.json` | `config_aws.json` | `dotnet_{platform}` | `platform` + `--cbs_version` + `setup_dir="QE"` |
| `sgw/` | `topology.json` | `config.json` | `sgw` | `setup_dir="QE"` |
| `upg-sgw/` | `topology.json` | `config.json` | `upg-sgw` | `setup_dir="QE"` |
| `es/` | **Custom** — `generate_topology()` | `config.json` | `es` | Calls `start_backend()` directly |
| `multiplatform/` | `topology.json` | `config_multiplatform.json` | varies | Own inline topology-composition logic, doesn't call shared `setup_test()` |

### Exceptions to the template

1. **`QE/es/setup_test.py`** — does NOT use `setup_test()`. Has its own `generate_topology()` and calls `start_backend()` directly with ES-specific CLI options (`--sgw-version`, `--cbs-version`).
2. **`dev_e2e/multipeer_functional/setup_test.py`** — builds a per-platform version map from its CLI options, then expands it (via `ts_to_topology`/`get_platform_version`) into a positional `cbl_versions` list matching its topology's `test_servers` order before calling `setup_test()`.
3. **`QE/multiplatform/setup_test.py`** — does not call the shared `setup_test()` at all; it has its own inline topology-composition logic.

## Shared Scripts (`shared/`)

### `setup_test.py` — Core Functions

**`setup_test(cbl_versions, sgw_versions, topology_file_in, config_file_in, topology_tag, couchbase_version="7.6", setup_dir="dev_e2e")`**
1. Reads the topology JSON template; rewrites `$schema` and `include` paths
2. Resolves CBS version and each entry in `sgw_versions` (via `proget` API)
3. Assigns `cbl_versions` positionally to `topology_file_in`'s `test_servers` (index 0 → server 0, etc.; the last entry repeats once the list is exhausted — see `distribute_versions`)
4. Assigns resolved `sgw_versions` the same way to `sync_gateways`, **but only when `sync_gateways` is defined directly in `topology_file_in`** — topologies that pull it in via `include` (e.g. the single-test-server dev_e2e/QE pipelines) always get one SGW at `defaults.sgw.version` (the first resolved version)
5. Sets `defaults.cbs.version` / `defaults.sgw.version`, `tag`
6. Writes final topology to `environment/aws/topology_setup/topology.json`
7. Downloads `cbbackupmgr` for the CBS version
8. Creates `TopologyConfig` → calls `start_backend()`

CLI wrappers accept comma-separated versions (`"4.0.0,4.1.0"`) and split them with `parse_versions()` before calling `setup_test()`.

**`ts_to_topology(ts_platform)`** — Maps platform tags to topology names: `swift_* → ios`, `jak_android → android`, `jak_* → java`, `dotnet_* → dotnet`, `c_* → c`.

### `config.sh` (and `config.psm1` for Windows)

Exports path constants used by every `test.sh` / `teardown.sh`:
```bash
PIPELINES_DIR, TESTS_DIR, ENVIRONMENT_DIR, TEST_SERVER_DIR,
SHARED_PIPELINES_DIR, DEV_E2E_PIPELINES_DIR, DEV_E2E_TESTS_DIR,
QE_TESTS_DIR, QE_PIPELINES_DIR, AWS_ENVIRONMENT_DIR
```
Functions: `move_artifacts()`, `find_dir()`, `print_box()`.

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
pushd $QE_TESTS_DIR > /dev/null            # or $DEV_E2E_TESTS_DIR
uv run pytest -v --no-header --config config.json [-m MARKER]
popd > /dev/null
```

### `QE/upg-sgw/test.sh` — unique pattern

1. Initial setup with the first SGW version → run `upg_sgw` tests.
2. Loop through remaining versions:
   - `stop_backend.py --destroy-sgw --no-ts-stop`
   - `start_backend.py --no-cbs-provision --no-es-provision --no-lb-provision --no-ls-provision --no-ts-run`
   - Run `upg_sgw` tests again.

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
                string(name: 'CBL_VERSION',  value: params.CBL_VERSION),
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

## Prebuild Pipeline (`prebuild/Jenkinsfile`)

Supported platform values: `dotnet_windows`, `dotnet_macos`, `dotnet_ios`, `dotnet_android`, `jak_android`, `jak_desktop`, `jak_webservice`, `swift_ios`, `c_ios`, `c_android`, `c_linux_x86_64`, `c_macos`, `c_windows`, `js`.

## Rules

- **`sys.path.append(str(SCRIPT_DIR.parents[3]))`** — every `setup_test.py` must add the repo root.
- **Use `click`** for CLI argument parsing in every Python script.
- **Use `setup_dir="QE"`** for QE pipelines (default is `"dev_e2e"`).
- **Topology and config JSONs are templates** — committed; final versions are generated at runtime.
- **Always call `move_artifacts`** in `teardown.sh`.
- **Teardown must run even on failure** — Jenkinsfile uses `post { always { … } }`.
- **Never commit generated files** — `config.json` in test dirs, `topology.json` in `topology_setup/`.
- **Python 3.10+** — `X | Y`, never `Union[X, Y]` / `Optional[X]`.
- **No markdown sidecars for pipeline changes** — code is self-documenting via shared scripts.

## Commands

```bash
# Pipelines are triggered via Jenkins UI; for local testing, invoke directly:

# Example: dev_e2e iOS setup
cd environment/aws
uv run ../jenkins/pipelines/dev_e2e/ios/setup_test.py 4.0.0 4.0.0

# Source shared bash config
source jenkins/pipelines/shared/config.sh
```

## Cross-References

| What | Where | Relationship |
|---|---|---|
| AWS orchestrator | [environment/aws/start_backend.py](../environment/aws/start_backend.py) | Called by `setup_test()` |
| AWS teardown | [environment/aws/stop_backend.py](../environment/aws/stop_backend.py) | Called by `teardown.sh` / `upg-sgw/test.sh` |
| Shared setup | [jenkins/pipelines/shared/setup_test.py](pipelines/shared/setup_test.py) | Core function all pipelines delegate to |
| Test suites | [tests/dev_e2e/](../tests/dev_e2e/), [tests/QE/](../tests/QE/) | What pipelines ultimately run |
| Test server source | [servers/](../servers/) | Built by the prebuild pipeline |
| Framework | [client/src/cbltest/](../client/src/cbltest/) | Consumed by the tests pipelines run |
| Topology schema | [environment/aws/topology_setup/topology_schema.json](../environment/aws/topology_setup/topology_schema.json) | Validates generated topology |
