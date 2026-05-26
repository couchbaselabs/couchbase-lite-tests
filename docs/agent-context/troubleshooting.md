# Troubleshooting

## Setup Failures

### `uv sync` fails or missing tools

- Check Python version: `python3 --version` (must be 3.10+).
- Re-run setup: `bash scripts/setup-hooks.sh`.
- Confirm `uv` is available: `uv --version`.

### Pre-commit hooks block commit

- Run full hook suite manually: `uv run pre-commit run --all-files`.
- Fix reported lint/type/format issues.
- If secrets are detected, rotate/remove secrets and update baseline only when appropriate.

## Test Execution Failures

### `--config` errors in pytest runs

- Ensure the command is run from expected directory (`tests/dev_e2e`, `tests/QE`, or `client/smoke_tests`).
- Confirm config file exists (`config.json` or `config_in.json`).
- Do not hand-edit generated test config used by CI setup.

### Topology marker skips or failures

- Verify environment has required counts (test servers, sync gateways, couchbase servers, load balancers).
- Confirm topology JSON and generated config align with marker requirements.

### API version mismatch between test servers

- Symptom: session startup/version resolution failures in `cbltest`.
- Ensure all test servers are running compatible builds and same supported API generation.
- Rebuild/redeploy test servers through orchestrator/prebuild path.

## Infrastructure Failures

### AWS orchestrator provisioning issues

- Verify AWS SSO session: run `aws sso login`.
- Validate Terraform availability (`terraform version`) and state consistency.
- Retry with targeted skip flags to isolate failing setup stage (`--no-*` options).

### Orphaned cloud resources

- Always teardown using `environment/aws/stop_backend.py`.
- For partial cleanup, use `--destroy-*` flags intentionally and document what was left running.

### Docker backend inconsistencies

- Docker flow is secondary and less maintained; prefer AWS for authoritative failures.
- If using Docker, confirm SGW/CBS containers are healthy before running tests.

## Logs and Evidence Locations

- Root-level logs: `testserver.log`, `http_log/`
- Test logs: `tests/session.log`, `tests/testserver.log`
- CI definitions: `.github/workflows/*.yml`, `jenkins/pipelines/`
- Environment scripts and templates: `environment/aws/*`, `environment/docker/*`

## Retry and Escalation Guidance

- Retry transient infra/network failures once after confirming credentials/session.
- For persistent failures, capture:
  - exact command
  - stack trace/error output
  - topology/config file used
  - recent related changes
- Escalate to the QE/infra team with those artifacts.

## Escalation

- For persistent infra failures, escalate through the repository issue or pull request you are working in, include the artifacts listed above, and request QE/infra team review. Avoid pinging individuals directly — route through the owning team.
