# CI/CD Pipelines — `jenkins/`

All Jenkins pipelines for building test servers, provisioning AWS environments, and running tests across every platform. Also contains the Jenkins server's own Docker setup.

## Scope

You own everything under `jenkins/`:
- `jenkins/pipelines/shared/` — scripts used by **all** pipelines
- `jenkins/pipelines/functional/` — pipelines that run `tests/functional`: one per CBL platform (`android`, `c`, `dotnet`, `ios`, `java`, `javascript`) plus `sgw` (`-m min_sync_gateways`) and `es` (`-m min_edge_servers`)
- `jenkins/pipelines/main/` — daily triggers: `cbl/` starts `e2e-functional-<platform>` for the latest build of every CBL train; `sgw/` starts `functional/sgw` for new Sync Gateway builds; `es/` starts `functional/es` for new Edge Server builds
- `jenkins/pipelines/upg-sgw/` — SGW upgrade pipelines (`tests/upgrade_sgw`)
- `jenkins/pipelines/multiplatform/` — multi-platform pipeline: runs `tests/multiplatform` with several test servers in one topology
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
│   │   ├── config.psm1                 # PowerShell equivalent (Windows pipelines)
│   │   ├── resolveProgetVersion.groovy # Version/train/prefix → concrete version via ProGet
│   │   ├── progetBuilds.groovy         # Version → [version, build]; non-EOL trains (get_trains)
│   │   ├── triggerRecord.groovy        # main/* "already triggered" record (~/.jenkins_build_info)
│   │   ├── cblSgwCompatibility.groovy  # Rejects CBL/SGW pairs that cannot replicate
│   │   └── productVersions.groovy      # Product under test + optional versions → resolved CBL/SGW/ES
│   │
│   ├── prebuild/                       # Test server prebuild
│   │   └── Jenkinsfile                 # Builds + uploads artifacts to latestbuilds
│   │
│   ├── functional/                     # Per-platform pipelines for tests/functional
│   │   ├── android/                    #   Jenkinsfile + test.sh + teardown.sh + setup_test.py + config.json + topology.json + logcat.py
│   │   ├── c/                          #   Jenkinsfile + run_test.sh/.ps1 + teardown.sh/.ps1 + setup_test.py + config.json + topologies/
│   │   ├── dotnet/                     #   Jenkinsfile + run_test.sh/.ps1 + teardown.sh/.ps1 + setup_test.py + config_aws.json + topologies/
│   │   ├── ios/                        #   Jenkinsfile + test.sh + teardown.sh + setup_test.py + config.json + topology_single_device.json
│   │   ├── java/                       #   Jenkinsfile + desktop/ + webservice/ (each run_test.sh/.ps1 + teardown.sh/.ps1 + setup_test.py + config + topology)
│   │   ├── javascript/                 #   Jenkinsfile + test.sh + teardown.sh + setup_test.py + config.json + topology_single_host.json
│   │   ├── sgw/                        #   Every min_sync_gateways test (multi-SGW topology + load balancer)
│   │   └── es/                         #   Every min_edge_servers test (own generate_topology(), topologies/)
│   │
│   ├── main/                           # Daily triggers
│   │   ├── cbl/                        #   e2e-functional-<platform> for every CBL train
│   │   ├── sgw/                        #   functional/sgw for new Sync Gateway builds
│   │   └── es/                         #   functional/es for new Edge Server builds
│   │
│   ├── upg-sgw/                        # SGW upgrade (iterates versions)
│   └── multiplatform/                  # tests/multiplatform (several test servers)
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

from jenkins.pipelines.shared.setup_test import VersionType, setup_test


@click.command()
@click.argument("cbl_versions", type=VersionType())
@click.argument("sgw_versions", type=VersionType())
def cli_entry(cbl_versions: list[str], sgw_versions: list[str]) -> None:
    setup_test(
        cbl_versions,
        sgw_versions,
        SCRIPT_DIR / "TOPOLOGY_FILE",  # ← varies per platform
        SCRIPT_DIR / "CONFIG_FILE",  # ← varies per platform
        "PLATFORM_TAG",  # ← varies per platform
        setup_dir="SUITE",  # "functional" (default) or "upgrade_sgw"
    )


if __name__ == "__main__":
    cli_entry()
```

### Per-pipeline arguments

| Pipeline | `topology_file` | `config_file` | `platform_tag` | Extra args |
|---|---|---|---|---|
| `functional/android/` | `topology.json` | `config.json` | `jak_android` | — |
| `functional/c/` | `topologies/topology_single_{platform}.json` | `config.json` | `c_{platform}` | `platform` positional |
| `functional/dotnet/` | `topologies/topology_single_{platform}.json` | `config_aws.json` | `dotnet_{platform}` | `platform` positional + `--cbs_version` |
| `functional/ios/` | `topology_single_device.json` | `config.json` | `swift_ios` | — |
| `functional/java/desktop/` | `topology_single_host.json` | `config_java_desktop.json` | `jak_desktop` | — |
| `functional/java/webservice/` | `topology_single_host.json` | `config_java_webservice.json` | `jak_webservice` | — |
| `functional/javascript/` | `topology_single_host.json` | `config.json` | `js` | — |
| `functional/sgw/` | `topology.json` | `config.json` | `sgw` | — |
| `upg-sgw/` | `topology.json` | `config.json` | `upg-sgw` | `setup_dir="upgrade_sgw"` |
| `functional/es/` | **Custom** — `generate_topology()` | `config.json` | `es` | Calls `start_backend()` directly |
| `multiplatform/` | `topology.json` | `config_multiplatform.json` | `multiplatform` | `setup_multiplatform.py` passes only the test servers `PLATFORM_VERSIONS` uses, `setup_dir="multiplatform"` |

### Exceptions to the template

1. **`functional/es/setup_test.py`** — does NOT use `setup_test()`. Has its own `generate_topology()` and calls `start_backend()` directly with ES-specific CLI options (`--sgw-version`, `--cbs-version`).
2. **`multiplatform/setup_multiplatform.py`** — not a thin wrapper: `setup_multiplatform.py` checks `PLATFORM_VERSIONS` against `topology.json` (every test server the agent can reach) and ProGet, then calls the shared `setup_test()` on just the test servers the entries use.

## Shared Scripts (`shared/`)

### `setup_test.py` — Core Functions

**`setup_test(cbl_versions, sgw_versions, topology_file_in, config_file_in, topology_tag, couchbase_version="7.6", setup_dir="functional", es_version=None)`**
1. Reads the topology JSON template; rewrites `$schema` and `include` paths
2. Resolves CBS version and each entry in `sgw_versions` (via `proget` API)
3. Assigns `cbl_versions` positionally to `topology_file_in`'s `test_servers` (index 0 → server 0, etc.; the last entry repeats once the list is exhausted — see `distribute_versions`)
4. Assigns resolved `sgw_versions` the same way to `sync_gateways`, **but only when `sync_gateways` is defined directly in `topology_file_in`** — topologies that pull it in via `include` (e.g. the single-test-server `functional/` pipelines) always get one SGW at `defaults.sgw.version` (the first resolved version)
5. Sets `defaults.cbs.version` / `defaults.sgw.version` (and `defaults.es.version` when `es_version` is given; otherwise Edge Servers get the latest release), `tag`
6. Writes final topology to `environment/aws/topology_setup/topology.json`
7. Downloads `cbbackupmgr` for the CBS version, and `bucketpool`
8. Creates `TopologyConfig` → calls `start_backend()`

CLI wrappers accept comma-separated versions (`"4.0.0,4.1.0"`) via the `VersionType` click param type, which converts the argument to a `list[str]` (using `parse_versions()`) before `cli_entry` ever sees it.

### `config.sh` (and `config.psm1` for Windows)

Exports path constants used by every `test.sh` / `teardown.sh`:
```bash
PIPELINES_DIR, TESTS_DIR, ENVIRONMENT_DIR, TEST_SERVER_DIR,
SHARED_PIPELINES_DIR, DEV_E2E_PIPELINES_DIR, QE_PIPELINES_DIR, AWS_ENVIRONMENT_DIR,
FUNCTIONAL_TESTS_DIR, SYSTEM_TESTS_DIR, UPGRADE_SGW_TESTS_DIR
```
Functions: `move_artifacts()`, `find_dir()`, `print_box()`.

### Groovy helpers (loaded with `load`)

Each is loaded inside a node context (`def x = load 'jenkins/pipelines/shared/<file>.groovy'`) and avoids default arguments, which the CPS transform does not handle reliably.

- `resolveProgetVersion.groovy` — `resolveProgetVersion(product, version, label[, includePrerelease])`: blank, train or prefix → newest concrete version (prereleases included unless `false`).
- `progetBuilds.groovy` — `resolveVersionBuild(proget, product, param, label, includePrerelease)` → `[version:, build:]` or `null` when the version has no published build yet; `fetchTrains(product)`; `getBuildNumber(product, version)`.
- `triggerRecord.groovy` — `readRecord(name)`, `alreadyTriggered(record, version, build)`, `saveRecord(name, record)` for the `{ "<version>": "<build>" }` record each `main/*` trigger keeps per job on its pinned agent.
- `cblSgwCompatibility.groovy` — `incompatibility(cblVersion, sgwVersion)`: a reason string, or `null` when the pair can replicate.
- `productVersions.groovy` — `resolve(underTest, cblProduct, params)`: requires the version of the product under test (`'cbl'`, `'sgw'` or `'es'`), resolves `CBL_VERSION`, `SGW_VERSION` and `ES_VERSION` (an empty optional one is the latest release), rejects an incompatible CBL/SGW pair, and sets `CBL_RESOLVED`, `SGW_RESOLVED`, `ES_RESOLVED`, `CBL_PREBUILD_VERSION` and `CBL_PREBUILD_BUILD`. See `pipelines/functional/AGENTS.md`.

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
pushd $FUNCTIONAL_TESTS_DIR > /dev/null     # or $SYSTEM_TESTS_DIR / $UPGRADE_SGW_TESTS_DIR
uv run pytest -v --no-header --config config.json [-m MARKER]
popd > /dev/null
```

### `upg-sgw/test.sh` — unique pattern

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
- **`setup_dir`** names the `tests/` suite that receives `config.json`: omit it for `functional` (the default); `upg-sgw` passes `"upgrade_sgw"`.
- **Topology and config JSONs are templates** — committed; final versions are generated at runtime.
- **Always call `move_artifacts`** in `teardown.sh`.
- **Teardown must run even on failure** — Jenkinsfile uses `post { always { … } }`.
- **Never commit generated files** — `config.json` in test dirs, `topology.json` in `topology_setup/`.
- **Python 3.13+** — modern syntax enforced by ruff `UP` + pyupgrade (see root [AGENTS.md](../AGENTS.md)).
- **No markdown sidecars for pipeline changes** — code is self-documenting via shared scripts.

## Commands

```bash
# Pipelines are triggered via Jenkins UI; for local testing, invoke directly:

# Example: iOS setup
cd environment/aws
uv run ../jenkins/pipelines/functional/ios/setup_test.py 4.0.0 4.0.0

# Source shared bash config
source jenkins/pipelines/shared/config.sh
```

## Cross-References

| What | Where | Relationship |
|---|---|---|
| AWS orchestrator | [environment/aws/start_backend.py](../environment/aws/start_backend.py) | Called by `setup_test()` |
| AWS teardown | [environment/aws/stop_backend.py](../environment/aws/stop_backend.py) | Called by `teardown.sh` / `upg-sgw/test.sh` |
| Shared setup | [jenkins/pipelines/shared/setup_test.py](pipelines/shared/setup_test.py) | Core function all pipelines delegate to |
| Test suites | [tests/functional/](../tests/functional/), [tests/system/](../tests/system/), [tests/upgrade_sgw/](../tests/upgrade_sgw/) | What pipelines ultimately run |
| Test server source | [servers/](../servers/) | Built by the prebuild pipeline |
| Framework | [client/src/cbltest/](../client/src/cbltest/) | Consumed by the tests pipelines run |
| Topology schema | [environment/aws/topology_setup/topology_schema.json](../environment/aws/topology_setup/topology_schema.json) | Validates generated topology |
