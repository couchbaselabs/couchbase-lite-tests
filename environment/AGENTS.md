# Infrastructure & Environment — `environment/`

All infrastructure provisioning for the test harness. The AWS orchestrator is primary — Terraform creates EC2 instances, then Python scripts SSH in and configure Couchbase Server (CBS), Sync Gateway (SGW), Edge Server (ES), load balancers, and LogSlurp. A Docker Compose stack exists for local development.

## Scope

You own everything under `environment/`:
- `environment/aws/` — AWS orchestrator (Terraform + Python SSH scripts, topology management)
- `environment/docker/` — local Docker Compose environment (CBS + SGW + LogSlurp)
- `environment/LogSlurp/` — C# log aggregation service
- `environment/otel-collector/` — OpenTelemetry collector config

You do **not** own `servers/`, `tests/`, or `client/`, but you deploy and configure the environments they depend on.

## Layout

```
environment/
├── aws/                                # AWS orchestrator (primary)
│   ├── start_backend.py                # Main entry — provisions everything
│   ├── stop_backend.py                 # Teardown — destroys resources
│   ├── main.tf                         # Terraform: EC2, VPC, subnets (us-east-1, AL2023)
│   ├── download_tool.py                # Downloads cbbackupmgr etc.
│   │
│   ├── common/                         # Shared utilities (reuse these — don't duplicate)
│   │   ├── docker.py                   # start_container(), remote_exec()
│   │   ├── io.py                       # download_progress_bar, sftp_progress_bar, tar/zip/untar, get_ec2_hostname
│   │   ├── output.py                   # header()
│   │   ├── terraform.py                # get_terraform_output(), get_terraform_json()
│   │   └── x509_certificate.py         # create_self_signed_certificate()
│   │
│   ├── server_setup/                   # CBS provisioning
│   │   ├── setup_server.py             # SSH → configure-system.sh → Docker → init cluster
│   │   ├── configure-node.sh
│   │   ├── configure-system.sh         # Disable THP, tune swappiness
│   │   └── shell2http/                 # HTTP wrapper for shell commands on EC2
│   │
│   ├── sgw_setup/                      # SGW provisioning
│   │   ├── setup_sgw.py                # SSH → upload RPM → install → bootstrap → start
│   │   ├── bootstrap.json, bootstrap-alternate.json
│   │   ├── cert/, config/
│   │   ├── start-sgw.sh.in
│   │   └── *.rpm                       # Pre-downloaded SGW RPMs
│   │
│   ├── es_setup/                       # Edge Server provisioning
│   │   ├── setup_edge_servers.py
│   │   ├── config/, dataset/
│   │
│   ├── lb_setup/                       # Load Balancer (Traefik)
│   │   ├── setup_load_balancers.py
│   │   ├── traefik.yml
│   │   └── http_config.yml.in
│   │
│   ├── logslurp_setup/                 # LogSlurp provisioning
│   │   ├── setup_logslurp.py
│   │   └── configure-system.sh
│   │
│   └── topology_setup/                 # Test server deployment + topology
│       ├── setup_topology.py           # TopologyConfig — parses topology JSON, manages test servers
│       ├── topology_schema.json, default_topology.json
│       ├── test_server.py              # TestServer abstract base + registry
│       ├── build_test_server.py        # Build & upload to latestbuilds
│       ├── cbl_library_downloader.py
│       └── test_server_platforms/
│           ├── platform_bridge.py      # PlatformBridge ABC (validate/install/run/stop/uninstall/get_ip)
│           ├── c_register.py           # c_macos, c_linux_x86_64, c_windows, c_ios, c_android
│           ├── dotnet_register.py      # dotnet_macos, dotnet_windows, dotnet_ios, dotnet_android
│           ├── swift_register.py       # swift_ios
│           ├── java_register.py        # jak_android, jak_desktop, jak_webservice
│           ├── js_register.py          # js
│           ├── exe_bridge.py           # ExeBridge for desktop/CLI servers
│           ├── macos_bridge.py
│           ├── android_bridge.py       # ADB
│           └── ios_bridge.py           # XHarness
│
├── docker/                             # Local Docker Compose (not actively maintained)
│   ├── docker-compose.yml              # CBS + SGW + LogSlurp services
│   ├── start_environment.py
│   ├── sample-config.json
│   ├── telemetry.yml
│   ├── cbs/                            # CBS Dockerfile + init scripts
│   └── sg/                             # SGW Dockerfile + config
│
├── LogSlurp/                           # C# log aggregation service
│   ├── LogSlurp.sln
│   ├── LogSlurp/                       # ASP.NET server (Dockerfile)
│   └── ClientLogger/                   # Client-side logging library
│
└── otel-collector/                     # OpenTelemetry collector
    └── config.yaml
```

## AWS Orchestrator

### `start_backend.py` — provision in order

```
1. terraform apply          → EC2 instances (main.tf)
2. server_setup/            → Couchbase Server (Docker container on EC2)
3. sgw_setup/               → Sync Gateway (RPM upload + install + bootstrap)
4. es_setup/                → Edge Server (upload + install)
5. lb_setup/                → Load Balancer (Traefik Docker container)
6. logslurp_setup/          → LogSlurp (Docker container)
7. topology_setup/          → Test servers (build/download → install → run)
8. Write TDK config.json    → Output for test suites
```

Skip flags: `--no-terraform-apply`, `--no-cbs-provision`, `--no-sgw-provision`, `--no-es-provision`, `--no-lb-provision`, `--no-ls-provision`, `--no-ts-run`.

Entry points:
- CLI: `cli_entry()` (via `@click.command()`) — direct command line use
- Programmatic: `script_entry(topology, config_in, config_out, steps)` — used by Jenkins

### `stop_backend.py` — teardown

Granular destruction: `--destroy-sgw`, `--destroy-cbs`, `--destroy-es`, `--destroy-lb`, `--destroy-ls`, `--no-ts-stop`. Without any of those flags, runs a full `terraform destroy`.

Granular destroy targets individual `aws_instance` resources by index, e.g. `-target=aws_instance.sync_gateway[0]`.

### Terraform (`main.tf`)

- Providers: `aws` (us-east-1), `random`, `tls`
- AMI: Amazon Linux 2023 (x86_64 + arm64)
- Pre-existing: VPC subnet 10.0.1.0/24, routing rules
- Required version: `>= 1.2.0`

## Setup Script Pattern (every `*_setup/setup_*.py`)

```python
import paramiko
from environment.aws.common.docker import start_container, remote_exec
from environment.aws.common.io import sftp_progress_bar, get_ec2_hostname
from environment.aws.common.output import header
from environment.aws.topology_setup.setup_topology import TopologyConfig


def main(topology: TopologyConfig) -> None:
    hostname = get_ec2_hostname(...)  # Hostname from Terraform state
    ssh = paramiko.SSHClient()
    ssh.connect(hostname, username="ec2-user", pkey=pkey)
    sftp_progress_bar(sftp, local_path, remote_path)  # Upload via SFTP
    remote_exec(ssh, "install_command", "Installing…")
    start_container(name, image, hostname, pkey, ...)  # Docker / systemd
```

## Topology System

### `TopologyConfig` (`topology_setup/setup_topology.py`)

- Parses topology JSON (CBS / SGW / ES / LB / test server counts + versions)
- Reads Terraform state via `read_from_terraform()` to discover EC2 hostnames
- Manages test server lifecycle: build → deploy → run → stop
- Properties: `total_cbs_count`, `total_sgw_count`, `total_es_count`, `total_lb_count`, `wants_logslurp`

### `TestServer` (`test_server.py`)

Abstract base with registry pattern:
- `TestServer.register(name)` — decorator
- `TestServer.create(name, version)` — factory
- `TestServer.initialize()` — imports all platform modules to trigger registration
- Abstract: `build()`, `compress_package()`, `uncompress_package()`, `create_bridge()`, `latestbuilds_path`, `platform`

### `PlatformBridge` (`test_server_platforms/platform_bridge.py`)

Abstract interface: `validate()`, `install()`, `run()`, `stop()`, `uninstall()`, `get_ip()`.

### Platform Registrations

| File | Platform Keys | Bridge Types |
|---|---|---|
| `c_register.py` | `c_macos`, `c_linux_x86_64`, `c_windows`, `c_ios`, `c_android` | `ExeBridge`, `iOSBridge`, `AndroidBridge` |
| `dotnet_register.py` | `dotnet_macos`, `dotnet_windows`, `dotnet_ios`, `dotnet_android` | `ExeBridge`, `macOSBridge`, `iOSBridge`, `AndroidBridge` |
| `swift_register.py` | `swift_ios` | `iOSBridge` |
| `java_register.py` | `jak_android`, `jak_desktop`, `jak_webservice` | `AndroidBridge`, `ExeBridge` |
| `js_register.py` | `js` | `ExeBridge` |

### Topology JSON Shape

```json
{
  "$schema": "topology_schema.json",
  "include": "default_topology.json",
  "defaults": { "cbs": { "version": "7.6.7" }, "sgw": { "version": "4.0.0" } },
  "tag": "platform_tag",
  "clusters": [{ "version": "7.6.7" }],
  "sync_gateways": [{ "version": "4.0.0" }],
  "test_servers": [{ "platform": "swift_ios", "cbl_version": "4.0.0" }],
  "edge_servers": [{ "version": "1.0.0" }],
  "load_balancers": [{}],
  "logslurp": true
}
```

## Docker Environment

⚠️ Not actively maintained — AWS is primary.

```bash
cd environment/docker && python start_environment.py
```

- Services: `cbl-test-cbs`, `cbl-test-sg`, `cbl-test-logslurp`
- Env vars: `COUCHBASE_VERSION`, `SG_DEB`

## Prerequisites (AWS)

- AWS SSO configured via Okta (`AWS_PROFILE` env var if not `default`)
- Terraform `>= 1.2.0`
- SSH config: `Host *.amazonaws.com` with `StrictHostKeyChecking accept-new`
- Git LFS (datasets)
- Python 3.10+ with `uv`
- iOS only: Xcode 16+, `libimobiledevice`, iPhone Private WiFi OFF

## Rules

- **Never commit** `terraform.tfstate` — gitignored, contains sensitive data
- **Always tear down via `stop_backend.py`** — prevents orphaned EC2 instances ($$$)
- **AWS SSO must be active** — `aws sso login` before any orchestrator op
- **Topology files are generated** by `jenkins/` setup scripts — don't hand-edit for CI
- **Python 3.10+** — `X | Y`, never `Union[X, Y]` / `Optional[X]`
- **`uv run` is required** for AWS scripts (uses root workspace deps — there is no separate `orchestrator` dep group)
- **Use `click`** for all CLI argument parsing
- **Use `paramiko`** for all SSH operations
- **Reuse `common/` utilities** — don't reinvent file transfer, Docker ops, or Terraform parsing

## Commands

```bash
# Install deps (from repo root)
uv sync

# Start full environment
cd environment/aws && uv run python start_backend.py \
  --topology topology_setup/topology.json \
  --tdk-config-in <template.json> \
  --tdk-config-out <output.json>

# Stop full environment
cd environment/aws && uv run python stop_backend.py \
  --topology topology_setup/topology.json

# Partial destroy (SGW only, keep test servers)
cd environment/aws && uv run python stop_backend.py \
  --topology topology_setup/topology.json --destroy-sgw --no-ts-stop

# Build & upload a test server
cd environment/aws && uv run python topology_setup/build_test_server.py \
  --platform swift_ios --version 4.0.0

# Local Docker
cd environment/docker && python start_environment.py
```

## Cross-References

| What | Where | Relationship |
|---|---|---|
| Test server source | [servers/](../servers/) | Built and deployed by `topology_setup/` |
| Platform bridges | [environment/aws/topology_setup/test_server_platforms/](aws/topology_setup/test_server_platforms/) | Platform-specific install/run/stop |
| Jenkins pipelines | [jenkins/pipelines/](../jenkins/pipelines/) | Call `start_backend.py`/`stop_backend.py` via `setup_test.py` |
| Test suites | [tests/dev_e2e/](../tests/dev_e2e/), [tests/QE/](../tests/QE/) | Consume the `config.json` this generates |
| Config parser | [client/src/cbltest/configparser.py](../client/src/cbltest/configparser.py) | Parses the config JSON this outputs |
| Topology schema | [aws/topology_setup/topology_schema.json](aws/topology_setup/topology_schema.json) | Validates topology JSON |
| Datasets | [dataset/](../dataset/) | Copied into test servers during build |
