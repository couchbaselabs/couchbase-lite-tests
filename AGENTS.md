# AGENTS.md — Couchbase Lite System Test Harness

## Project Purpose and Scope

This repository validates Couchbase Lite behavior across platform test servers against Sync Gateway and Couchbase Server.
It includes:
- Python test framework in `client/` (`cbltest`)
- System test suites in `tests/dev_e2e/` and `tests/QE/`
- Environment provisioning in `environment/` (AWS primary, Docker secondary)
- Platform server implementations in `servers/`
- CI orchestration in `jenkins/` and `.github/workflows/`

Use existing workflow commands and fixtures; do not invent alternate stacks.

## Core Commands

Run from repo root unless noted.

```bash
uv sync
bash scripts/setup-hooks.sh
uv run ruff check .
uv run ruff format .
uv run --group lint ty check
uv run pre-commit run --all-files
uv run -- pytest --config client/tests/empty_config.json client/tests
cd tests/dev_e2e && uv run pytest -x -v --config config.json
cd tests/QE && uv run pytest -x -v --config config.json
cd client/smoke_tests && uv run pytest -x -v --config config_in.json
cd environment/aws && uv run python start_backend.py --topology topology_setup/topology.json
cd environment/aws && uv run python stop_backend.py --topology topology_setup/topology.json
```

## Repo Layout

- `client/`: `cbltest` package, pytest plugins, smoke tests
- `tests/`: `dev_e2e` and `QE` suites plus fixtures/logs
- `servers/`: C, .NET, iOS, JVM, JavaScript test server implementations
- `environment/aws/`: Terraform + Python orchestrator for CBS/SGW/ES/LB/LogSlurp/test servers
- `environment/docker/`: local Docker environment
- `jenkins/pipelines/`: dev_e2e/QE platform setup and execution pipelines
- `spec/`: OpenAPI and test specifications
- `dataset/`: datasets used by tests

## Development Patterns and Constraints

- Python baseline is 3.10+ (`X | Y`, not `Union` / `Optional`).
- Async patterns are standard for test and framework I/O (`aiohttp`, `pytest-asyncio`).
- `config.json` in test directories is generated; do not hand-edit for CI workflows.
- Maintain compatibility for request/response API versions v1 and v2 in `client/src/cbltest/v1` and `v2`.
- Reuse existing marker and fixture patterns:
  - topology markers (`min_test_servers`, `min_sync_gateways`, etc.)
  - `cblpytest` fixture
  - `dataset_path` fixture
- Prefer shared orchestration/utilities over duplication:
  - `environment/aws/common/*`
  - `jenkins/pipelines/shared/*`
- Keep platform behavior behind existing bridge/registration abstractions in `environment/aws/topology_setup/test_server_platforms/`.

## Validation and Evidence Before Completion

Before finishing any change, provide evidence from applicable validators:

1. Lint/format: `uv run ruff check .` and `uv run ruff format .` (or check mode as required by task)
2. Type checks: `uv run --group lint ty check` (the `lint` group contains `ty`; use it for all paths including orchestrator)
3. Hooks when relevant: `uv run pre-commit run --all-files`
4. Tests scoped to changed area:
   - `client/`: `uv run -- pytest --config client/tests/empty_config.json client/tests` and/or `client/smoke_tests`
   - `tests/dev_e2e` or `tests/QE`: run targeted pytest command with `--config`
   - `environment/` changes: run the touched script CLI `--help` and dry-run-safe checks where possible

If full integration tests are not runnable locally, state exactly what was run and what remains.

## Security and Sensitive Paths

- Never commit secrets, keys, tokens, certificates, or Terraform state.
- Treat these as sensitive:
  - `.secrets.baseline`
  - `environment/aws/temp.pem`
  - `environment/aws/terraform.tfstate*` (if present locally)
  - generated configs containing hostnames/credentials
- Use `detect-secrets` findings and any configured pre-commit findings as blockers, not warnings.
- Avoid logging credentials or signed URLs in test output and fixtures.

## Supporting Agent Context

- `docs/architecture.agents.md` — runtime boundaries and end-to-end flow
- `docs/agent-context/repo-inventory.md` — tools, directories, configs, unknowns
- `docs/agent-context/build-test-matrix.md` — copy-pasteable validation commands by component
- `docs/agent-context/domain-glossary.md` — system terms and acronyms
- `docs/agent-context/troubleshooting.md` — common setup/CI/test failures
