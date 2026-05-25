# CLAUDE.md — Couchbase Lite System Test Harness

> **Current Instruction Version:** 2.0  
> **Last Updated:** March 2026  
> **Status:** Stable & Verified for universal AI agent/IDE compatibility

## Project Overview

This is the **Couchbase Lite System Test Harness** (internally called "TDK"). It runs system-level
tests requiring multiple components — a Couchbase Lite instance, Sync Gateway (SGW), and Couchbase
Server (CBS) — to verify Couchbase Lite releases across all supported platforms.

## Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────────────┐
│   Environment    │────▶│   Client (TDK)   │────▶│     Test Servers         │
│  CBS + SGW + ES  │     │ Python framework │     │ C│.NET│iOS│JVM│JS        │
│  (Docker / AWS)  │     │ `cbltest` package│     │ (per-platform binaries)  │
└──────────────────┘     └────────┬─────────┘     └──────────────────────────┘
                                  │
                          ┌───────▼────────┐
                          │     Tests      │
                          │  dev_e2e / QE  │
                          └────────────────┘
```

## Directory Map

| Directory        | What It Contains                                                                                       |
|------------------|--------------------------------------------------------------------------------------------------------|
| `client/`        | Python `cbltest` package — core test framework, pytest plugins, request/response API                   |
| `tests/dev_e2e/` | Developer E2E test suite (12 test files)                                                               |
| `tests/QE/`      | QA test suite (18+ test files, edge server, SGW upgrade, etc.)                                         |
| `servers/`       | Per-platform test server implementations: `c/`, `dotnet/`, `ios/`, `jak/`, `javascript/`               |
| `environment/`   | Infrastructure: `aws/` (Terraform + orchestrator), `docker/` (compose), `LogSlurp/`, `otel-collector/` |
| `jenkins/`       | CI/CD: per-platform Jenkins pipelines in `pipelines/{dev_e2e,QE}/{platform}/`                          |
| `spec/`          | OpenAPI spec (`api/api.yaml`), test specifications (markdown), dataset docs                            |
| `dataset/`       | Test datasets: cblite2 databases, SG configs, blobs                                                    |

## Toolchain & Commands

### Prerequisites

- Python 3.10+ (via `uv`)
- `uv` package manager (https://docs.astral.sh/uv/)
- Git LFS (must be installed *before* cloning)

### Setup After Cloning

```bash
# Install all pre-commit and commit-msg hooks
bash scripts/setup-hooks.sh
```

This sets up Python dependencies, installs `pre-commit` and `detect-secrets` via `uv tool`, and activates git hooks.

### Common Commands

```bash
# Install all dependencies (root workspace)
uv sync

# Run developer E2E tests
cd tests/dev_e2e && uv run pytest -x -v --config config.json

# Run QE tests
cd tests/QE && uv run pytest -x -v --config config.json

# Run smoke tests
cd client/smoke_tests && uv run pytest -x -v --config config_in.json

# Lint & format (Python)
uv run ruff check .
uv run ruff format .

# Type check
uv run --group lint ty check

# Pre-commit (all hooks: ruff, ty, pyupgrade, shebang checks, secrets scan, conventional commits)
uv run pre-commit run --all-files

# Start local Docker environment (CBS + SGW + LogSlurp)
cd environment/docker && python start_environment.py

# Start AWS environment (requires SSO login)
cd environment/aws && python start_backend.py --topology topology_setup/topology.json

# Stop AWS environment
cd environment/aws && python stop_backend.py --topology topology_setup/topology.json
```

### Git Hooks

All hooks are enforced automatically on commit via `.pre-commit-config.yaml`:

- **Syntax & Style**: ruff (lint + import sorting), ruff-format, pyupgrade, ty check
- **Merge Safety**: check-merge-conflict
- **Commit Format**: Conventional Commits validation (`<type>[scope]: <description>`)

See `scripts/hooks/check-commit-msg.sh` for commit message validation and `.pre-commit-config.yaml` for full hook configuration.

### Python Workspace Structure

This is a `uv` workspace with two members:

- **Root** (`pyproject.toml`) — top-level project, depends on `cbltest`
- **`client/`** (`client/pyproject.toml`) — the `cbltest` package (hatchling build)

Dependency groups in root:

- `orchestrator` — deps for AWS orchestrator scripts
- `lint` — lint tools (ty, ruff, type stubs)

## Coding Standards

### Python Style

- **Python 3.10+ minimum** — use `X | Y` union syntax, never `Union[X, Y]` or `Optional[X]`
- `pyupgrade --py310-plus` enforced via pre-commit
- `ruff` for linting (with import sorting via `I` rules) and formatting
- `ty` for type checking (configured in `[tool.ty.environment]` in `pyproject.toml`)
- All test I/O is **async** using `aiohttp` + `pytest-asyncio`

### Test Conventions

- Test files: `test_<feature>.py`
- Test functions: `async def test_<descriptive_name>(...)`
- Use `cblpytest` fixture (auto-injected by `cbltest.plugins.cblpytest_fixture`)
- Use `dataset_path` fixture for dataset file paths (defined in each `conftest.py`)
- Mark with `@pytest.mark.sgw`, `@pytest.mark.cbl`, or `@pytest.mark.upg_sgw`
- Use topology markers: `@pytest.mark.min_test_servers(N)`, `@pytest.mark.min_sync_gateways(N)`
- QE tests have automatic cleanup via `cleanup_after_test` fixture

### Request/Response Versioning

- API versions: v1 and v2 (in `client/src/cbltest/v1/` and `v2/`)
- Registration decorators: `@register_request(TestServerRequestType.X, version=N)`, `@register_body(...)`
- Available versions checked via `version.py::available_api_version()` (currently v1 and v2)

### Config Files

- Test config JSON schema: `https://packages.couchbase.com/couchbase-lite/testserver.schema.json`
- Topology JSON schema: `environment/aws/topology_setup/topology_schema.json`
- Config/topology files are **generated** by setup scripts, not hand-edited in test dirs

## Key Repetitive Patterns (Know Before Editing)

### Jenkins Pipelines

Every `jenkins/pipelines/{dev_e2e,QE}/{platform}/setup_test.py` follows the same template:

1. Set SCRIPT_DIR → 2. Import `setup_test` from shared → 3. `@click.command()` CLI → 4. Call `setup_test(...)` with
   platform-specific strings.

Only differences: `platform_name`, `topology_file` path, `config_file` path.

### conftest.py Dataset Fixtures

Three nearly identical `dataset_path` fixtures exist in `tests/dev_e2e/conftest.py`, `tests/QE/conftest.py`,
`client/smoke_tests/conftest.py`. They differ only in relative path depth.

### Server Build Scripts

Each platform under `servers/` has build scripts (`download_cbl.sh`, `build_*.sh`) following the same logical flow:
download CBL → build → package.

## CI/CD

### GitHub Actions

- `python_verify.yml` — On push/PR to Python files: runs `ty check`, `ruff format --check`, `ruff check`
- `openapi.yml` — On changes to `spec/api/`: Redocly lint, yamllint, preview link in PRs

### Jenkins

- `jenkins/pipelines/prebuild/` — Build test server artifacts
- `jenkins/pipelines/dev_e2e/{platform}/` — Per-platform dev E2E pipelines
- `jenkins/pipelines/QE/{platform}/` — Per-platform QA pipelines
- All use shared scripts from `jenkins/pipelines/shared/`

## Instruction Files at a Glance

| File                               | Purpose                                          | For Whom                      |
|------------------------------------|--------------------------------------------------|-------------------------------|
| `/CLAUDE.md`                       | Master project overview                          | Everyone                      |
| `/.github/copilot-instructions.md` | GitHub Copilot-specific directives               | Copilot users                 |
| `/README.md`                       | Getting started guide                            | New contributors              |
| `{subdir}/CLAUDE.md`               | Domain-specific context (architecture, patterns) | Humans, documentation readers |
| `{subdir}/AGENTS.md`               | AI agent personas for that domain                | AI agents, IDE chatbots       |

## Sub-directory Agents

Each subdirectory contains two complementary instruction files for domain-specific guidance:

### Context Files (CLAUDE.md)

Detailed architectural documentation for human understanding:

- `client/CLAUDE.md` — cbltest framework architecture, APIs, patterns
- `tests/CLAUDE.md` — test suite structure, fixtures, markers, datasets
- `servers/CLAUDE.md` — per-platform implementations, build scripts, deployment
- `environment/CLAUDE.md` — AWS orchestrator, Terraform, topology management
- `jenkins/CLAUDE.md` — CI/CD pipeline patterns, per-platform configurations
- `spec/CLAUDE.md` — OpenAPI specification, test specs, dataset documentation

### Agent Personas (AGENTS.md)

Specialized AI agent instructions for code generation and assistance:

- `client/AGENTS.md` — cbltest framework agent (request/response versioning, plugins)
- `tests/AGENTS.md` — test writer agent (test patterns, fixtures, markers)
- `servers/AGENTS.md` — platform server agent (multi-language implementations)
- `environment/AGENTS.md` — infrastructure agent (orchestration, provisioning)
- `jenkins/AGENTS.md` — CI/CD agent (pipeline templates, repetitive patterns)
- `spec/AGENTS.md` — specification agent (API spec, test specs, contracts)

**When working in a subdirectory:** Check both `CLAUDE.md` (for context) and `AGENTS.md` (for AI-guided development)

## Quick Start for AI Agents

If you're an AI agent (Claude, Copilot, Gemini, Codeium, Factory.ai), here's how to use this guidance:

1. **Start here:** Read this root `CLAUDE.md` for project overview
2. **Pick your domain:** Based on where you'll make changes, read the corresponding `CLAUDE.md` in that subdirectory
3. **Get specialized guidance:** Read the `AGENTS.md` in that subdirectory for your role-specific instructions
4. **Example:** Working on tests?
    - Start: `/CLAUDE.md` (project overview)
    - Context: `tests/CLAUDE.md` (test structure, fixtures, patterns)
    - Role: `tests/AGENTS.md` (test writer agent instructions)

Every AI agent should adopt the persona defined in the `AGENTS.md` file of the domain you're working in.

### ⚠️ Important: Markdown Documentation Files

**DO NOT create markdown files to document code changes.** Markdown files (`CLAUDE.md`, `AGENTS.md`, `CLAUDE_*.md`, `ENHANCEMENT_*.md`, etc.) are **for AI understanding and repository structure only**. 

When you make actual code changes (add tests, modify helpers, update implementations):
- ✅ **DO:** Create/modify the actual code files (`.py`, `.yaml`, etc.)
- ❌ **DON'T:** Create markdown documentation files explaining those changes
- ❌ **DON'T:** Create `ENHANCEMENT_SUMMARY.md`, `IMPLEMENTATION_GUIDE.md`, etc. for each change

**Only markdown files that belong in the repo:**
- `CLAUDE.md` — architectural documentation (per-directory)
- `AGENTS.md` — AI agent instructions (per-directory)
- `README.md` — getting started guides
- `spec/*.md` — test specifications and dataset docs

All other markdown is documentation for AI agents to understand the codebase, not for describing individual code changes. The code itself is self-documenting via `spec/` files and comments.

