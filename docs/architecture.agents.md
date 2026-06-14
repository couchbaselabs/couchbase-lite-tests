# Architecture for Agents

## System Boundary

This repo is a system-test harness, not the product runtime itself.
It coordinates infrastructure, platform test servers, and Python tests to validate Couchbase Lite behavior.

## High-Level Flow

1. Provision backend + test-server topology (`environment/aws` or `environment/docker`)
2. Generate/consume test config JSON
3. Execute Python suites (`tests/dev_e2e`, `tests/QE`, or `client/smoke_tests`)
4. Tests call `cbltest` APIs (`client/src/cbltest`)
5. `cbltest` sends versioned REST requests to platform test servers (`servers/*`)
6. Servers execute CBL operations and return typed responses
7. Results/logs feed local output and CI systems (GitHub Actions/Jenkins)

## Module Boundaries

| Module | Responsibility | Key Paths |
|---|---|---|
| Framework | Request factory, API wrappers, pytest plugins, config parsing | `client/src/cbltest/` |
| Test suites | Scenario orchestration and assertions | `tests/dev_e2e/`, `tests/QE/` |
| Platform servers | Platform-specific execution of CBL operations | `servers/` |
| Environment | Provisioning and lifecycle of CBS/SGW/ES/LB/LogSlurp/test servers | `environment/aws/`, `environment/docker/` |
| CI/CD | Repeatable validation and pipeline setup | `.github/workflows/`, `jenkins/pipelines/` |
| Contract/spec | API and scenario specs | `spec/api/`, `spec/tests/` |
| Data | Test datasets and configs | `dataset/` |

## Runtime Contracts and Coupling

- Tests rely on `cblpytest` fixture contract and marker-based topology constraints.
- `cbltest` relies on request/response registration by `TestServerRequestType` + API version.
- All test servers in a session must negotiate the same API version.
- Environment output config must match schema and provide reachable service endpoints.

## Validation Clues by Change Area

- `client/` changes: run `ruff`, `ty`, `client/tests`, and smoke tests where impacted.
- `tests/` changes: run suite-local pytest command with valid `--config`.
- `environment/aws` changes: run static checks plus script-level validation (`--help`, safe path checks), then targeted provisioning test if available.
- CI workflow changes: validate YAML and mirror affected command locally where possible.

## Typical Failure Surfaces

- Invalid/missing config JSON path
- Topology mismatch with pytest markers
- API version disagreement across test servers
- AWS credentials/session/terraform drift
- Secrets detection failures in hooks

## Unknowns

- Full ownership map for each subsystem and explicit on-call rotation is not encoded in the repository.
