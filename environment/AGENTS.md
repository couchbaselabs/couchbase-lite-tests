# Agent: Infrastructure & Environment (environment/)

## Identity

You are a specialized agent for the infrastructure provisioning layer of the Couchbase Lite
System Test Harness. You manage the AWS orchestrator (Terraform + Python SSH scripts), the
Docker Compose local environment, LogSlurp, and the topology system that builds and deploys
per-platform test servers to EC2 instances or local devices.

## Scope

You own all code under `environment/`:
- `environment/aws/` — AWS orchestrator (Terraform, Python setup scripts, topology management)
- `environment/docker/` — Docker Compose local environment (CBS + SGW + LogSlurp)
- `environment/LogSlurp/` — C# log aggregation service
- `environment/otel-collector/` — OpenTelemetry collector config

You do NOT own the test servers (`servers/`), test suites (`tests/`), or the test framework
(`client/`), but you deploy and configure the environments they depend on.

## AWS Orchestrator — Core Flow

### `start_backend.py` (the main entry point)
Provisions in this exact order:
```
1. terraform apply          → EC2 instances (main.tf)
2. server_setup/            → Couchbase Server (Docker container on EC2)
3. sgw_setup/               → Sync Gateway (RPM upload + install + bootstrap)
4. es_setup/                → Edge Server (upload + install)
5. lb_setup/                → Load Balancer (Traefik Docker container)
6. logslurp_setup/          → LogSlurp (Docker container)
7. topology_setup/          → Test servers (build/download → install → run)
8. Write config.json        → Output config for test suites
```

Skip flags: `--no-terraform-apply`, `--no-cbs-provision`, `--no-sgw-provision`,
`--no-es-provision`, `--no-lb-provision`, `--no-ls-provision`, `--no-ts-run`

Entry points:
- CLI: `cli_entry()` via `@click.command()` — used directly from command line
- Programmatic: `script_entry(topology, config_in, config_out, steps)` — used by Jenkins pipelines

### `stop_backend.py` (teardown)
Supports granular destruction: `--destroy-sgw`, `--destroy-cbs`, `--destroy-es`,
`--destroy-lb`, `--destroy-ls`, `--no-ts-stop`

Without specific flags → full `terraform destroy`.

Granular destroy targets individual `aws_instance` resources by index, e.g.:
`-target=aws_instance.sync_gateway[0]`

### Terraform (`main.tf`)
- Provider: `aws` (us-east-1), `random`, `tls`
- AMI: Amazon Linux 2023 (x86_64 and arm64)
- Resources: EC2 instances for CBS, SGW, ES, LB, LogSlurp
- Pre-existing: VPC subnet 10.0.1.0/24, routing rules
- Required version: `>= 1.2.0`

## Setup Script Pattern (All `*_setup/` follow this)

```python
# Every setup_*.py follows this structure:
import paramiko
from environment.aws.common.docker import start_container, remote_exec
from environment.aws.common.io import sftp_progress_bar, get_ec2_hostname
from environment.aws.common.output import header
from environment.aws.topology_setup.setup_topology import TopologyConfig

def main(topology: TopologyConfig) -> None:
    # 1. Get hostname from Terraform state
    hostname = get_ec2_hostname(...)
    # 2. SSH in via paramiko
    ssh = paramiko.SSHClient()
    ssh.connect(hostname, username="ec2-user", pkey=pkey)
    # 3. Upload configs via SFTP
    sftp_progress_bar(sftp, local_path, remote_path)
    # 4. Execute remote commands
    remote_exec(ssh, "install_command", "Installing...")
    # 5. Start service
    start_container(name, image, hostname, pkey, ...)
```

## Shared Utilities (`common/`)

| File | Purpose | Key Functions |
|------|---------|---------------|
| `docker.py` | Remote Docker via SSH | `start_container()`, `remote_exec()` |
| `io.py` | File operations | `download_progress_bar()`, `sftp_progress_bar()`, `tar_directory()`, `untar_directory()`, `zip_directory()`, `unzip_directory()`, `get_ec2_hostname()` |
| `output.py` | CLI formatting | `header()` |
| `terraform.py` | Terraform state | `get_terraform_output()`, `get_terraform_json()` |
| `x509_certificate.py` | TLS certs | `create_self_signed_certificate()` |

## Topology System (`topology_setup/`)

### TopologyConfig (`setup_topology.py`)
Central class that:
- Parses topology JSON (CBS/SGW/ES/LB/test server counts + versions)
- Reads Terraform state to discover EC2 hostnames via `read_from_terraform()`
- Manages test server lifecycle: build → deploy → run → stop
- Properties: `total_cbs_count`, `total_sgw_count`, `total_es_count`, `total_lb_count`, `wants_logslurp`

### TestServer (`test_server.py`)
Abstract base class with registry pattern:
- `TestServer.register(name)` — decorator to register platform subclasses
- `TestServer.create(name, version)` — factory method
- `TestServer.initialize()` — imports all platform modules to trigger registration
- Abstract methods: `build()`, `compress_package()`, `uncompress_package()`, `create_bridge()`, `latestbuilds_path`, `platform`

### PlatformBridge (`test_server_platforms/platform_bridge.py`)
Abstract interface: `validate()`, `install()`, `run()`, `stop()`, `uninstall()`, `get_ip()`

### Platform Registrations
| File | Platforms | Bridge Type |
|------|-----------|-------------|
| `c_register.py` | `c_macos`, `c_linux`, `c_windows`, `c_ios`, `c_android` | `ExeBridge`, `iOSBridge`, `AndroidBridge` |
| `dotnet_register.py` | `dotnet_macos`, `dotnet_linux`, `dotnet_windows` | `ExeBridge`, `MacOSBridge` |
| `swift_register.py` | `swift_ios` | `iOSBridge` |
| `java_register.py` | `jak_android`, `jak_desktop`, `jak_webservice` | `AndroidBridge`, `ExeBridge` |
| `js_register.py` | `js` | `ExeBridge` |

### Topology JSON Schema
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

⚠️ No longer actively maintained. AWS is primary.

```bash
cd environment/docker && python start_environment.py
```
- Services: `cbl-test-cbs`, `cbl-test-sg`, `cbl-test-logslurp`
- Env vars: `COUCHBASE_VERSION`, `SG_DEB`

## Coding Rules

- **Python 3.10+**: always `X | Y`, never `Union[X, Y]` or `Optional[X]`
- **Use `click`** for all CLI argument parsing
- **Use `paramiko`** for all SSH operations
- **Use `common/` utilities** — don't reinvent file transfer, Docker ops, or Terraform parsing
- **Never commit `terraform.tfstate`** — contains sensitive data
- **Always use `stop_backend.py`** to tear down — orphaned EC2 instances cost money
- **AWS SSO must be active** — `aws sso login` before any orchestrator operation
- **Use `uv run`** for AWS scripts

## Commands
```bash
# Install deps
uv sync

# Start full
cd environment/aws && uv run python start_backend.py \
  --topology topology_setup/topology.json \
  --tdk-config-in <template> --tdk-config-out <output>

# Stop full
cd environment/aws && uv run python stop_backend.py \
  --topology topology_setup/topology.json

# Partial destroy (SGW only)
python stop_backend.py --topology topology_setup/topology.json --destroy-sgw --no-ts-stop

# Build + upload test server
python topology_setup/build_test_server.py --platform swift_ios --version 4.0.0

# Docker local
cd environment/docker && python start_environment.py
```

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| Test server source code | `servers/` | Built and deployed by `topology_setup/` |
| Jenkins pipelines | `jenkins/pipelines/` | Call `start_backend.py`/`stop_backend.py` via `setup_test.py` |
| Test suites | `tests/dev_e2e/`, `tests/QE/` | Consume the `config.json` this generates |
| Framework config parser | `client/src/cbltest/configparser.py` | Parses the config JSON this outputs |
| Topology schema | `topology_setup/topology_schema.json` | Validates topology JSON files |
| Datasets | `dataset/` | Copied into test servers during build |

