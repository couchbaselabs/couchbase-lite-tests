# Local Environment Setup

This directory contains scripts to help set up and run a local testing environment.

## Quickstart

`start_local.py` builds/starts the test server and Sync Gateway in one go:

```bash
# Rosmar
uv run environment/local/start_local.py --server rosmar --repo-path /path/to/sync-gateway

# Couchbase Server
uv run environment/local/start_local.py --server cbs --repo-path /path/to/sync-gateway --connstr couchbase://127.0.0.1
```

The test server and Sync Gateway stages can be skipped independently with
`--skip-testserver`, `--skip-sync-gateway-build`, and `--skip-sync-gateway-start` —
useful for iterating without repeating the earlier, slower steps. `--repo-path`/`--git-tag`
are only required unless `--skip-sync-gateway-build` is set, and `--connstr` is only valid
with `--server cbs` (defaults to `$SG_TEST_COUCHBASE_SERVER_URL`).

`start_local.py` also writes the path of the cbltest config to use for the run to
`environment/local/topology_config`, so it can be passed straight to pytest:

```bash
cd tests/dev_e2e
uv run pytest --config "$(cat ../../environment/local/topology_config)"
```

## Running the individual steps

`build_sync_gateway.py` and `run_sync_gateway.py` have been folded into `start_local.py`.
Use its `--skip-*` flags to rebuild/restart just one stage, e.g. to rebuild Sync Gateway
without touching the test server:

```bash
uv run environment/local/start_local.py --server rosmar --repo-path /path/to/sync-gateway --skip-testserver
```

To stop the background Sync Gateway process independently:

```bash
uv run environment/local/start_local.py --stop-sync-gateway
```

- **Logs:** Written to `environment/local/sync_gateway.log`.
- **Configuration:**
  - `--server rosmar`: uses `environment/local/sync_gateway_config/basic_sync_gateway_rosmar.json`
  - `--server cbs`: uses `environment/local/sync_gateway_config/basic_sync_gateway_cbs.json` (with `bootstrap.server` overridden by `--connstr`, if given)

## Running Tests

After starting the environment, you can run tests against it:

```bash
cd tests/dev_e2e

# If using Couchbase Server (cbs)
uv run pytest --config ../../environment/local/topology_configs/cbs_config.json

# If using Rosmar
uv run pytest --config ../../environment/local/topology_configs/rosmar_config.json
```
