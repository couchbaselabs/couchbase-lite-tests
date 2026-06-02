# Copilot Instructions — Couchbase Lite System Test Harness

## What This Project Is

This is the **Couchbase Lite System Test Harness** ("TDK"). It runs multi-device system tests
(Couchbase Lite ↔ Sync Gateway ↔ Couchbase Server) to verify Couchbase Lite releases on all
platforms (C, .NET, iOS/Swift, JVM/Kotlin, JavaScript).

## Architecture Overview

```
Environment (CBS + SGW)  →  Client/TDK (Python)  →  Test Servers (C/.NET/iOS/JVM/JS)
                                    ↓
                             Tests (dev_e2e / QE)
```

- `client/` — Python `cbltest` package: test framework, pytest plugins, request/response types
- `tests/dev_e2e/` — Developer E2E tests; `tests/QE/` — QA tests
- `servers/{c,dotnet,ios,jak,javascript}/` — Per-platform test server implementations
- `environment/{aws,docker}/` — Infrastructure (Terraform, Docker Compose)
- `jenkins/pipelines/` — Per-platform CI/CD pipelines
- `spec/api/api.yaml` — OpenAPI spec defining the test server REST API

## Coding Standards

### Python (client/, tests/, environment/, jenkins/)

- **Python 3.10+ required** — use `X | Y` syntax, not `Union[X, Y]` or `Optional[X]`
- `ruff` for linting + formatting; `ty` for type checking; `pyupgrade --py310-plus`
- All test code is **async** (`pytest-asyncio`, `aiohttp`)
- Package manager: `uv` (workspace: root `pyproject.toml` + `client/pyproject.toml`)

### Test Patterns

- Files: `test_<feature>.py`; Functions: `async def test_<name>(...)`
- Use `cblpytest` fixture (auto-injected) and `dataset_path` fixture
- Mark tests: `@pytest.mark.sgw`, `@pytest.mark.cbl`, `@pytest.mark.upg_sgw`
- Topology markers: `@pytest.mark.min_test_servers(N)`, `@pytest.mark.min_sync_gateways(N)`
- QE tests get auto-cleanup via `cleanup_after_test` fixture in conftest.py

### API Versioning (client/src/cbltest/)

- Request/response types versioned in `v1/` and `v2/` subdirectories
- Registration via decorators: `@register_request(TestServerRequestType.X, version=N)`
- New request type? Add to `TestServerRequestType` enum → create v1/v2 impl → register

### Jenkins Pipelines (Highly Repetitive)

- `jenkins/pipelines/{dev_e2e,QE}/{platform}/setup_test.py` — all near-identical
- They import `setup_test` from `jenkins/pipelines/shared/setup_test.py`
- Differ only in: platform name string, topology file path, config file path

## Key Commands

```bash
uv sync                              # Install deps
uv run pytest -x -v --config ...     # Run tests
uv run ruff check .                  # Lint
uv run ruff format .                 # Format
uv run pre-commit run --all-files    # All pre-commit hooks
```

## Agent Delegation

For domain-specific AI agent guidance, check the `AGENTS.md` files in each subdirectory:

- `client/AGENTS.md` — cbltest framework
- `tests/AGENTS.md` — test suites (dev_e2e + QE)
- `servers/AGENTS.md` — per-platform test server implementations
- `environment/AGENTS.md` — infrastructure (AWS orchestrator, Docker, Terraform)
- `jenkins/AGENTS.md` — CI/CD pipelines (per-platform Jenkins jobs)
- `spec/AGENTS.md` — API spec, test specs, dataset docs

## What NOT To Do

- Don't use `Union[X, Y]` or `Optional[X]` — use `X | Y` and `X | None`
- Don't hardcode server URLs in tests — use config fixtures
- Don't hand-edit `config.json` or `topology.json` in test dirs — they are generated
- Don't commit `terraform.tfstate`, `testserver.log`, `session.log`, `http_log/`, `.venv/`
