# CLAUDE.md — Infrastructure & Environment (environment/)

## What This Is

This directory contains all infrastructure provisioning for the test harness. The AWS
orchestrator is the primary system — it uses Terraform to create EC2 instances, then
Python scripts to SSH in and configure Couchbase Server, Sync Gateway, Edge Server,
load balancers, and LogSlurp. A Docker Compose setup exists for local development.

## Directory Structure

```
environment/
├── aws/                        # AWS orchestrator (primary)
│   ├── start_backend.py        # Main entry — provisions everything
│   ├── stop_backend.py         # Teardown — destroys resources
│   ├── main.tf                 # Terraform config (EC2, VPC, subnets)
│   ├── download_tool.py        # Downloads cbbackupmgr and other tools
│   ├── requirements.txt        # Python deps for orchestrator
│   │
│   ├── common/                 # Shared utilities
│   │   ├── docker.py           # Remote Docker operations via SSH (start_container, remote_exec)
│   │   ├── io.py               # File I/O: download_progress_bar, sftp_progress_bar, tar/zip/untar
│   │   ├── output.py           # CLI output formatting (header)
│   │   ├── terraform.py        # Terraform output parsing (get_terraform_output, get_terraform_json)
│   │   └── x509_certificate.py # X.509 cert generation for TLS tests
│   │
│   ├── server_setup/           # Couchbase Server provisioning
│   │   ├── setup_server.py     # SSH → configure-system.sh → Docker container → init cluster
│   │   ├── configure-node.sh   # CBS node initialization script
│   │   ├── configure-system.sh # Disable THP, tune swappiness
│   │   └── shell2http/         # HTTP wrapper for shell commands on EC2
│   │
│   ├── sgw_setup/              # Sync Gateway provisioning
│   │   ├── setup_sgw.py        # SSH → upload RPM → install → bootstrap → start
│   │   ├── bootstrap.json      # Default SGW bootstrap config
│   │   ├── bootstrap-alternate.json  # Alternate bootstrap configs
│   │   ├── cert/               # TLS certificates for SGW
│   │   ├── config/             # SGW config templates
│   │   ├── start-sgw.sh.in     # SGW start script template
│   │   └── *.rpm               # Pre-downloaded SGW RPM files
│   │
│   ├── es_setup/               # Edge Server provisioning
│   │   ├── setup_edge_servers.py  # SSH → upload → install → start
│   │   ├── config/             # ES config templates
│   │   └── dataset/            # ES-specific dataset files
│   │
│   ├── lb_setup/               # Load Balancer provisioning
│   │   ├── setup_load_balancers.py  # SSH → Traefik container setup
│   │   ├── traefik.yml         # Traefik static config
│   │   └── http_config.yml.in  # Dynamic routing config template
│   │
│   ├── logslurp_setup/         # LogSlurp provisioning
│   │   ├── setup_logslurp.py   # SSH → Docker container setup
│   │   └── configure-system.sh # System configuration
│   │
│   └── topology_setup/         # Test server deployment & topology management
│       ├── setup_topology.py   # TopologyConfig class — parses topology JSON, manages test servers
│       ├── topology_schema.json # JSON schema for topology files
│       ├── default_topology.json # Default topology config
│       ├── test_server.py      # TestServer abstract base class (build, download, compress, bridge)
│       ├── build_test_server.py # Build & upload test servers to latestbuilds
│       ├── cbl_library_downloader.py  # Download CBL library for test servers
│       └── test_server_platforms/     # Per-platform implementations
│           ├── platform_bridge.py     # PlatformBridge ABC (validate, install, run, stop, uninstall, get_ip)
│           ├── c_register.py          # C platform variants (macOS, Linux, Windows, iOS, Android)
│           ├── dotnet_register.py     # .NET platform variants
│           ├── swift_register.py      # iOS/Swift platform
│           ├── java_register.py       # JVM/Kotlin platform variants
│           ├── js_register.py         # JavaScript platform
│           ├── exe_bridge.py          # Bridge for executable-based servers (C, .NET desktop)
│           ├── macos_bridge.py        # macOS-specific bridge
│           ├── android_bridge.py      # Android ADB bridge
│           └── ios_bridge.py          # iOS XHarness bridge
│
├── docker/                     # Local Docker Compose environment
│   ├── docker-compose.yml      # CBS + SGW + LogSlurp services
│   ├── start_environment.py    # Brings up compose, waits for SGW readiness
│   ├── sample-config.json      # Example TDK config for Docker environment
│   ├── telemetry.yml           # OpenTelemetry config for Docker
│   ├── cbs/                    # CBS Dockerfile + init scripts
│   └── sg/                     # SGW Dockerfile + config
│
├── LogSlurp/                   # C# log aggregation service
│   ├── LogSlurp.sln            # .NET solution
│   ├── LogSlurp/               # Server project (ASP.NET, Dockerfile)
│   └── ClientLogger/           # Client-side logging library
│
└── otel-collector/             # OpenTelemetry collector
    └── config.yaml             # Collector pipeline configuration
```

## AWS Orchestrator Flow

### `start_backend.py` — The Main Orchestrator
Provisions the full environment in order:

```
1. terraform apply          (main.tf → EC2 instances)
2. server_setup/            (CBS → Docker container → cluster init)
3. sgw_setup/               (SGW → upload RPM → install → bootstrap)
4. es_setup/                (Edge Server → upload → install)
5. lb_setup/                (Load Balancer → Traefik container)
6. logslurp_setup/          (LogSlurp → Docker container)
7. topology_setup/          (Test servers → build/download → install → run)
8. Write TDK config.json    (output file for test suites)
```

Each step can be skipped with `--no-*` flags:
`--no-terraform-apply`, `--no-cbs-provision`, `--no-sgw-provision`,
`--no-es-provision`, `--no-lb-provision`, `--no-ls-provision`, `--no-ts-run`

### `stop_backend.py` — Teardown
Destroys resources. Supports granular destruction:
`--destroy-sgw`, `--destroy-cbs`, `--destroy-es`, `--destroy-lb`, `--destroy-ls`, `--no-ts-stop`

Without specific flags, does full `terraform destroy`.

### TopologyConfig (`topology_setup/setup_topology.py`)
Central class that:
- Parses topology JSON files (defines CBS/SGW/ES/LB/test server counts and versions)
- Reads Terraform state to discover EC2 hostnames
- Manages test server lifecycle (build → deploy → run → stop)

### Topology JSON Structure
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

## Setup Script Pattern (Repetitive)

All `*_setup/setup_*.py` files follow the same structure:
1. SSH into EC2 instance via `paramiko`
2. Upload config files via SFTP (`sftp_progress_bar`)
3. Execute remote shell commands (`remote_exec`)
4. Start service (Docker container or systemd)

Common imports: `paramiko`, `click`, and utilities from `common/`.

## Docker Environment

⚠️ **Note**: Docker backend is no longer actively maintained. AWS is the primary backend.

```bash
# Start local environment
cd environment/docker && python start_environment.py

# Env vars:
#   COUCHBASE_VERSION=7.6.4
#   SG_DEB=<url-to-sgw-deb>
```

Services: `cbl-test-cbs` (CBS), `cbl-test-sg` (SGW), `cbl-test-logslurp` (LogSlurp)

## Prerequisites (AWS)
- AWS SSO configured via Okta (`AWS_PROFILE` env var if not "default")
- Terraform installed (`>= 1.2.0`)
- SSH config: `Host *.amazonaws.com` with `StrictHostKeyChecking accept-new`
- Git LFS (for dataset files)
- Python 3.10+ with `uv`
- iOS only: Xcode 16+, `libimobiledevice`, iPhone Private WiFi OFF

## Commands
```bash
# Install orchestrator deps
cd environment/aws && uv sync

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

# Build test server
cd environment/aws && uv run python topology_setup/build_test_server.py \
  --platform swift_ios --version 4.0.0

# Start Docker local
cd environment/docker && python start_environment.py
```

## Rules
- **Never commit** `terraform.tfstate` — it's gitignored and contains sensitive data
- **Always use `stop_backend.py`** to tear down — prevents orphaned EC2 instances ($$$)
- **AWS SSO must be active** — run `aws sso login` before orchestrator
- **Topology files are generated** by `jenkins/` setup scripts, not hand-edited for CI
- **Python 3.10+**: use `X | Y`, never `Union[X, Y]` or `Optional[X]`
- **`uv run`** is required for AWS scripts (uses orchestrator deps)

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| Test server source | `servers/` | Built and deployed by `topology_setup/` |
| Platform bridges | `topology_setup/test_server_platforms/` | Platform-specific install/run/stop |
| Jenkins pipelines | `jenkins/pipelines/` | Call `start_backend.py`/`stop_backend.py` |
| Test suites | `tests/dev_e2e/`, `tests/QE/` | Consume the `config.json` this generates |
| Test framework | `client/src/cbltest/configparser.py` | Parses the config.json this generates |
| Topology schema | `topology_setup/topology_schema.json` | Validates topology JSON files |
| Datasets | `dataset/` | Copied into test servers during build |

