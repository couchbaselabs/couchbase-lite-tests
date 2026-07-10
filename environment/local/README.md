# Local Environment Setup

This directory contains scripts to help set up and run a local testing environment.

## Building Sync Gateway

Use `build_sync_gateway.py` to compile Sync Gateway from source. This requires `go` to be installed on your system.

```bash
# Build from an existing local repository
uv run environment/local/build_sync_gateway.py --repo-path /path/to/sync-gateway

# Build from a specific git tag/branch (clones to environment/local/sync_gateway_clone)
uv run environment/local/build_sync_gateway.py --git-tag release/3.3.0
```

## Running Sync Gateway

Once built, you can manage the Sync Gateway process using `run_sync_gateway.py`. You must provide either `--start` (with a `--server` type) or `--stop`.

```bash
# Start Sync Gateway in the background using Rosmar
uv run environment/local/run_sync_gateway.py --start --server rosmar

# Start Sync Gateway in the background using CBS
uv run environment/local/run_sync_gateway.py --start --server cbs

# Stop the background Sync Gateway process
uv run environment/local/run_sync_gateway.py --stop
```

- **Logs:** Written to `environment/local/sync_gateway.log`.
- **Configuration:** 
  - `--server rosmar`: uses `environment/local/sync_gateway_config/basic_sync_gateway_rosmar.json`
  - `--server cbs`: uses `environment/local/sync_gateway_config/basic_sync_gateway_cbs.json`

## Running the Test Server

To start the local test server (CBL-C):

```bash
uv run environment/local/start_local.py
```

By default this downloads a prebuilt test server. To build it from source
instead, pass `--build-testserver` with a version string:

```bash
uv run environment/local/start_local.py --build-testserver 4.0.3
```

## Running Tests

After starting the environment, you can run tests against it:

```bash
cd tests/dev_e2e

# If using Couchbase Server (cbs)
uv run pytest --config ../../environment/local/cbs_config.json

# If using Rosmar
uv run pytest --config ../../environment/local/rosmar_config.json
```
