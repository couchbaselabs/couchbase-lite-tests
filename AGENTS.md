# Couchbase Lite System Test Harness (TDK)

System-level test harness for Couchbase Lite releases across all supported platforms. Drives per-platform test servers from a Python framework against Sync Gateway (SGW) and Couchbase Server (CBS).

## Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────────────┐
│   Environment    │────▶│   Client (TDK)   │────▶│     Test Servers         │
│  CBS + SGW + ES  │     │ Python framework │     │ C │ .NET │ iOS │ JVM │ JS│
│  (AWS / Docker)  │     │ `cbltest` package│     │ (per-platform binaries)  │
└──────────────────┘     └────────┬─────────┘     └──────────────────────────┘
                                  │
                          ┌───────▼────────┐
                          │     Tests      │
                          │  dev_e2e / QE  │
                          └────────────────┘
```

## Directory Map

| Path             | Contents                                                                                  | Sub-doc                                     |
|------------------|-------------------------------------------------------------------------------------------|---------------------------------------------|
| `client/`        | `cbltest` Python framework, pytest plugins, request/response API                          | [client/AGENTS.md](client/AGENTS.md)        |
| `tests/`         | `dev_e2e/` (12 test modules + 1 data helper) and `QE/` (20 tests + 12 edge-server tests)  | [tests/AGENTS.md](tests/AGENTS.md)          |
| `servers/`       | Per-platform test servers: `c/`, `dotnet/`, `ios/`, `jak/`, `javascript/`                 | [servers/AGENTS.md](servers/AGENTS.md)      |
| `environment/`   | `aws/` (Terraform + orchestrator), `docker/`, `LogSlurp/`, `otel-collector/`              | [environment/AGENTS.md](environment/AGENTS.md) |
| `jenkins/`       | CI/CD pipelines under `pipelines/{dev_e2e,QE}/{platform}/`                                | [jenkins/AGENTS.md](jenkins/AGENTS.md)      |
| `spec/`          | OpenAPI spec (`api/api.yaml`), test specs, dataset docs                                   | [spec/AGENTS.md](spec/AGENTS.md)            |
| `dataset/`       | Test datasets: cblite2 databases, SGW configs, blobs                                      | —                                           |

## Prerequisites

- Python 3.10+
- `uv` ([docs](https://docs.astral.sh/uv/))
- Git LFS (install **before** cloning — the repo carries binary datasets via LFS)

## Setup

```bash
bash scripts/setup-hooks.sh   # installs uv (if missing), syncs deps, installs git hooks
```

## Core Commands

Run from repo root unless noted.

```bash
# Install deps
uv sync

# Lint & format
uv run ruff check .
uv run ruff format .

# Type check
uv run --group lint ty check

# Pre-commit suite
uv run pre-commit run --all-files

# Framework tests (used in CI)
uv run -- pytest --config client/tests/empty_config.json client/tests

# Smoke tests
cd client/smoke_tests && uv run pytest -x -v --config config_in.json

# dev_e2e / QE suites
cd tests/dev_e2e && uv run pytest -x -v --config config.json
cd tests/QE      && uv run pytest -x -v --config config.json

# AWS environment (requires `aws sso login`)
cd environment/aws && uv run python start_backend.py --topology topology_setup/topology.json
cd environment/aws && uv run python stop_backend.py  --topology topology_setup/topology.json

# Local Docker environment (CBS + SGW + LogSlurp)
cd environment/docker && python start_environment.py
```

## Python Workspace

`uv` workspace with two members:
- Root `pyproject.toml` — top-level project, depends on `cbltest`
- `client/pyproject.toml` — the `cbltest` package (hatchling build)

Dependency groups in root:
- `lint` — `ty`, `ruff`, type stubs (use `uv run --group lint …`)

AWS orchestrator scripts run from the root workspace — there is **no** separate `orchestrator` group.

## Coding Standards

- **Python 3.10+** — use `X | Y`, never `Union[X, Y]` / `Optional[X]`. Enforced by `pyupgrade --py310-plus` in pre-commit.
- **Async everywhere** — test and framework I/O use `aiohttp` + `pytest-asyncio`.
- **Formatting / linting** — `ruff` (with `I` import sorting) and `ruff-format`.
- **Type checking** — `ty` (config in `[tool.ty.environment]`).
- **Request/response versioning** — API v1 and v2 live in `client/src/cbltest/v1/` and `v2/`. Register via `@register_request(TestServerRequestType.X, version=N)` and `@register_body(...)`. `version.py::available_api_version()` is the source of truth.
- **Reuse shared utilities** — `environment/aws/common/*`, `jenkins/pipelines/shared/*`. Don't reinvent file transfer, Docker ops, or Terraform parsing.

## Test Conventions

- Test files: `test_<feature>.py`; functions: `async def test_<…>(...)`.
- Use the `cblpytest` fixture (auto-injected by `cbltest.plugins.cblpytest_fixture`).
- Use the `dataset_path` fixture (defined per-suite in `conftest.py`).
- Topology markers: `@pytest.mark.min_test_servers(N)`, `@pytest.mark.min_sync_gateways(N)`, etc.
- Behavior markers: `@pytest.mark.sgw`, `.cbl`, `.upg_sgw`.
- QE tests auto-clean via the `cleanup_after_test` fixture.

## Config Files (Generated — Do Not Hand-Edit)

- Test config: `tests/{dev_e2e,QE}/config.json` (schema: `https://packages.couchbase.com/couchbase-lite/testserver.schema.json`)
- Topology: `environment/aws/topology_setup/*.json` (schema: `topology_schema.json`)

## Branching

`main` and `release/X.Y` split authority (full rationale: [docs/adr/0001-main-and-release-branch-strategy.md](docs/adr/0001-main-and-release-branch-strategy.md)):

- **Tests always come from `main`.** Never run or consult a `release/X.Y` branch's `tests/` — it is a stale byproduct of the branch point, never executed by CI, and misleading.
- **Test-server source is version-specific.** Each `release/X.Y` freezes test-server code at the last state compatible with the Couchbase Lite `X.Y` SDK line (breaking API changes across versions make a single-branch/conditional approach impossible — the JVM server has no preprocessor at all). The prebuild pipeline picks the branch from `CBL_VERSION`, falling back to `main` when no release branch exists.
- **Propagation is forward-only.** Fixes land on `main`, then cherry-pick back to release branches. Release branches never merge into `main`.

## Git Hooks

`.pre-commit-config.yaml` enforces on every commit:
- **Syntax / style**: ruff (lint + import sort), ruff-format, pyupgrade, ty
- **Merge safety**: check-merge-conflict, check-executables-have-shebangs, check-shebang-scripts-are-executable

`scripts/setup-hooks.sh` additionally installs `detect-secrets` and generates `.secrets.baseline` for **manual** scans. It is not wired into pre-commit — run `detect-secrets scan --baseline .secrets.baseline` manually before pushing changes that touch credentials, hostnames, or generated configs.

## Recurring Patterns (Know Before Editing)

1. **Jenkins per-platform `setup_test.py`** — every file under `jenkins/pipelines/{dev_e2e,QE}/{platform}/` is a thin click wrapper calling `setup_test(...)` from `jenkins/pipelines/shared/`. Only `platform_name`, `topology_file`, and `config_file` differ.
2. **`conftest.py` `dataset_path` fixtures** — three near-identical copies in `tests/dev_e2e/`, `tests/QE/`, `client/smoke_tests/` differing only in relative depth to `dataset/sg/`.
3. **Server build scripts** — every platform under `servers/` follows: `download_cbl.sh` → `build_*.sh` → package.
4. **AWS setup scripts** — every `environment/aws/*_setup/setup_*.py` follows: SSH via `paramiko` → SFTP upload → `remote_exec` → start service (Docker / systemd).

## CI/CD

- `.github/workflows/python_verify.yml` — runs `ty check`, `ruff format --check`, `ruff check` on Python changes.
- `.github/workflows/openapi.yml` — Redocly lint + yamllint on `spec/api/` changes; posts PR preview link.
- `jenkins/pipelines/prebuild/` — builds test-server artifacts.
- `jenkins/pipelines/{dev_e2e,QE}/{platform}/` — per-platform CI runs.

## Validation Before Completion

For every code change provide evidence from applicable validators:

1. Lint/format: `uv run ruff check .` and `uv run ruff format .`
2. Types: `uv run --group lint ty check`
3. Hooks: `uv run pre-commit run --all-files`
4. Tests scoped to the changed area:
   - `client/` → `client/tests` and/or `client/smoke_tests`
   - `tests/dev_e2e` or `tests/QE` → targeted pytest with `--config`
   - `environment/` → run the touched script with `--help` and dry-run-safe checks

If full integration tests are not runnable locally, state exactly what was run and what remains.

## Security & Sensitive Paths

- **Never commit**: secrets, keys, tokens, certificates, or Terraform state.
- Treat as sensitive: `.secrets.baseline`, `environment/aws/temp.pem`, `environment/aws/terraform.tfstate*`, generated configs containing hostnames/credentials.
- Avoid logging credentials or signed URLs in test output and fixtures.

## Markdown Discipline

Markdown files in this repo serve a narrow purpose. **Do not** create new markdown files to document code changes (e.g. `ENHANCEMENT_SUMMARY.md`, `IMPLEMENTATION_GUIDE.md`). Code changes belong in code; PR descriptions explain motivation.

Markdown files that belong in the repo:
- `AGENTS.md` — single source of truth per directory (this file and its peers); `CLAUDE.md` is a one-line import of the same content for Claude Code's auto-loading.
- `README.md` — getting-started guides.
- `spec/**/*.md` — API supplements, test specifications, dataset docs.

## Supporting Agent Context

- [docs/architecture.agents.md](docs/architecture.agents.md) — runtime boundaries and end-to-end flow
- [docs/agent-context/repo-inventory.md](docs/agent-context/repo-inventory.md) — tools, directories, configs
- [docs/agent-context/build-test-matrix.md](docs/agent-context/build-test-matrix.md) — copy-pasteable validation commands
- [docs/agent-context/domain-glossary.md](docs/agent-context/domain-glossary.md) — system terms and acronyms
- [docs/agent-context/troubleshooting.md](docs/agent-context/troubleshooting.md) — common setup/CI/test failures
