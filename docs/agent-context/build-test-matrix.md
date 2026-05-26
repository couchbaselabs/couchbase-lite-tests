# Build & Test Matrix

All commands are copy-pasteable and use the repo's existing toolchain.

## Baseline Setup

```bash
uv sync
bash scripts/setup-hooks.sh
```

## Global Validation

| Category | Command | Notes |
|---|---|---|
| Lint | `uv run ruff check .` | Includes import sorting checks (`I` rules). |
| Format | `uv run ruff format .` | Use `--check` in CI-equivalent runs. |
| Typecheck | `uv run --group lint ty check` | Root + `client/src` type environment. |
| Pre-commit suite | `uv run pre-commit run --all-files` | Runs ruff, ruff-format, pyupgrade, ty, merge-conflict/shebang checks, and the commit-msg conventional-commits hook. Secrets scanning is not wired into pre-commit; run `detect-secrets scan --baseline .secrets.baseline` manually. |

## Component-Specific Validation

| Component | Command | Scope |
|---|---|---|
| `client/` tests | `uv run -- pytest --config client/tests/empty_config.json client/tests` | Framework tests used in GitHub workflow. |
| `client/smoke_tests` | `cd client/smoke_tests && uv run pytest -x -v --config config_in.json` | Smoke checks requiring config file. |
| `tests/dev_e2e` | `cd tests/dev_e2e && uv run pytest -x -v --config config.json` | Full developer E2E suite. |
| `tests/QE` | `cd tests/QE && uv run pytest -x -v --config config.json` | Full QE suite. |
| `tests/QE` SGW subset | `cd tests/QE && uv run pytest -x -v --config config.json -m sgw` | Marker-focused validation. |
| AWS orchestrator lint/type | `uv run --group lint ty check` | Recommended when touching `environment/aws`. |

## Infrastructure Control Flows

| Flow | Command |
|---|---|
| Start AWS backend | `cd environment/aws && uv run python start_backend.py --topology topology_setup/topology.json --tdk-config-in <template.json> --tdk-config-out <output.json>` |
| Stop AWS backend | `cd environment/aws && uv run python stop_backend.py --topology topology_setup/topology.json` |
| Start local Docker backend | `cd environment/docker && python start_environment.py` |

## CI Evidence

- GitHub Actions Python checks: `.github/workflows/python_verify.yml`
  - `ty check` via `.github/workflows/verify_python.sh`
  - `ruff format --check`
  - `ruff` lint
  - `client/tests` command with `empty_config.json`
- OpenAPI checks: `.github/workflows/openapi.yml`
  - Redocly lint on `spec/api/api.yaml`
  - `yamllint` on `spec/`

## Team Defaults

- For doc-only edits, run basic checks.
- Prefer AWS-backed validation flows over Docker for authoritative validation.
