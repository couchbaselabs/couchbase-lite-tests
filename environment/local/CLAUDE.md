# Local Test Environment

Run the full TDK stack (Sync Gateway + test server) on your own machine, against either **rosmar**
(in-memory, no Couchbase Server needed) or **cbs** (real Couchbase Server). This is the fastest
inner loop for debugging a single failing test — no AWS provisioning, no Terraform, full local logs.

Run all commands from the repo root.

## One-time setup

Build Sync Gateway once (requires `go`):

```bash
uv run environment/local/build_sync_gateway.py --git-tag release/3.3.0   # or --repo-path /path/to/sync-gateway
```

This produces `environment/local/sync_gateway` and, if using `--git-tag`, clones the source into
`environment/local/sync_gateway_clone`.

Start the local test server (downloads or builds CBL-C, registers it as `localhost:8080`):

```bash
uv run environment/local/start_local.py
```

Run this again any time you need to **restart the test server** (e.g. after it crashes or hangs
mid-test) — it's safe to re-run.

## Running against rosmar (no Couchbase Server needed)

```bash
uv run environment/local/run_sync_gateway.py --start --server rosmar
uv run pytest --config ./environment/local/topologies/rosmar_config.json ./tests/QE --cbl-log-level debug
```

## Running against cbs (requires a local Couchbase Server on localhost)

```bash
uv run environment/local/run_sync_gateway.py --start --server cbs
uv run pytest --config ./environment/local/topologies/cbs_config.json ./tests/QE --cbl-log-level debug
```

`cbs_config.json` expects Couchbase Server reachable at `localhost` with `Administrator` /
`password` RBAC credentials — start/configure it yourself before running Sync Gateway against it.

Swap `./tests/QE` for `./tests/dev_e2e` to run the dev_e2e suite instead. Use `-k <expr>` or a
specific test file/id to target a single test while debugging.

### Running multiple Sync Gateway instances

Add `--count N` to start N instances, each on its own public/admin ports (4984/4985, 4986/4987,
4988/4989, ...):

```bash
uv run environment/local/run_sync_gateway.py --start --server rosmar --count 3
```

Instance 0 uses the checked-in config (`sync_gateway_config/basic_sync_gateway_*.json`) as-is;
instances 1+ get a generated `sync_gateway_config/<server>_instance_<n>.generated.json` with ports
offset. Logs land in `sync_gateway.log` (instance 0) and `sync_gateway_<n>.log` (instance n>0).
`--stop` terminates all running instances regardless of how many were started.

Point pytest at `topologies/3sgw_node_rosmar_config.json` or `topologies/3sgw_node_cbs_config.json`
to exercise all 3 (`sync-gateways` entries on ports 4984/4985, 4986/4987, 4988/4989):

```bash
uv run environment/local/run_sync_gateway.py --start --server rosmar --count 3
uv run pytest --config ./environment/local/topologies/3sgw_node_rosmar_config.json ./tests/QE --cbl-log-level debug
```

## Stopping Sync Gateway

```bash
uv run environment/local/run_sync_gateway.py --stop
```

## Debugging Sync Gateway itself

If a test failure traces back to Sync Gateway (not the test server/CBL), you can debug it in
place: `build_sync_gateway.py --git-tag ...` clones SGW source into
`environment/local/sync_gateway_clone` on first use, and that clone persists — point
`--repo-path` at it to rebuild after editing the source (e.g. adding logging or fixing a bug) or
attaching a debugger:

```bash
uv run environment/local/build_sync_gateway.py --repo-path ~/repos/couchbase-lite-tests/environment/local/sync_gateway_clone
uv run environment/local/run_sync_gateway.py --start --server rosmar   # or --server cbs
```

Repeat that rebuild step after every source change, then re-run the failing test. `run_sync_gateway.py --start` stops any previously running instance first, so the new binary always takes effect.

## Why use this instead of AWS

Everything runs as local processes, so you can attach a debugger, tail logs live, and iterate in
seconds instead of waiting on Terraform + EC2 provisioning. Reach for `environment/aws/` instead
when you need multi-node topologies, TLS, Edge Server, or CI-parity behavior.

## Logs — check these first when a test fails

| Component | Log file |
|---|---|
| Sync Gateway | `environment/local/sync_gateway.log` |
| Test server (CBL-C) | `servers/downloaded/c_macos/<version>/server.log` (path varies by platform/version — check what `start_local.py` downloaded/built) |

`--cbl-log-level debug` on the pytest invocation controls the *client-side* CBL log verbosity
written into the test server's own log; it does not affect Sync Gateway's log level.

## Notes

- `run_sync_gateway.py --start` always stops any existing local Sync Gateway process first, so it's
  safe to switch between `rosmar` and `cbs` by just re-running `--start --server <other>`.
- Config files under `topologies/` (`rosmar_config.json`, `cbs_config.json`,
  `3sgw_node_rosmar_config.json`, `3sgw_node_cbs_config.json`) are the generated-style TDK config
  for this local setup — see the repo-root [`AGENTS.md`](../../AGENTS.md) config note if changing
  shape.
