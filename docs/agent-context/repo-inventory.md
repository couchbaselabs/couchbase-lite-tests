# Repo Inventory

## Languages and Primary Tooling

| Area | Language(s) | Build/Test Tooling |
|---|---|---|
| Root orchestration scripts and tests | Python | `uv`, `pytest`, `ruff`, `ty`, `pre-commit` |
| `client/` framework | Python | `hatchling`, `pytest`, pytest plugin entry points |
| `environment/LogSlurp` | C# | `.sln` project + Dockerfile |
| `servers/` | C, C#, Swift/iOS, JVM/Kotlin, JavaScript | platform-specific build scripts |
| CI | YAML + Python helpers | GitHub Actions + Jenkins |

## Key Directories

- `client/src/cbltest/`: request/response APIs, plugin fixtures, v1/v2 protocol support
- `client/smoke_tests/`: smoke validation entry points
- `tests/dev_e2e/`, `tests/QE/`: system test suites and `conftest.py` fixtures
- `environment/aws/`: Terraform + Python orchestrator (`start_backend.py`, `stop_backend.py`)
- `environment/docker/`: local compose-based backend
- `jenkins/pipelines/`: shared and platform-specific setup/test pipeline code
- `spec/api/api.yaml`: OpenAPI contract
- `dataset/`: test datasets and SG configs

## Important Config and Control Files

- Root: `pyproject.toml`, `.pre-commit-config.yaml`, `.secrets.baseline`
- Client package: `client/pyproject.toml`
- CI: `.github/workflows/python_verify.yml`, `.github/workflows/openapi.yml`
- Topology schema: `environment/aws/topology_setup/topology_schema.json`
- Test config schema: `https://packages.couchbase.com/couchbase-lite/testserver.schema.json`

## Test Entry Points

- Framework unit-ish tests: `uv run -- pytest --config client/tests/empty_config.json client/tests`
- Smoke tests: `cd client/smoke_tests && uv run pytest -x -v --config config_in.json`
- Dev E2E: `cd tests/dev_e2e && uv run pytest -x -v --config config.json`
- QE: `cd tests/QE && uv run pytest -x -v --config config.json`

## Runtime Boundaries

- Tests call `cbltest` APIs (`client/`) which issue REST operations to platform test servers (`servers/`).
- Environment scripts provision CBS/SGW/ES/LB/LogSlurp and emit config consumed by tests.
- Jenkins and GitHub Actions run validation and platform pipelines, not product runtime logic.

## Team Defaults

- Doc-only edits: run basic checks.
- Validation backend preference: AWS.
- Infra escalation point: route via the repo owners/team channel.
