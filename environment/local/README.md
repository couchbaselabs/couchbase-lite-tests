# Local Environment Setup

This directory contains scripts to help set up and run a local testing environment.

## Quickstart

`--server rosmar` runs Sync Gateway against `rosmar`, its built-in in-memory storage engine —
no Couchbase Server needed, so it starts almost instantly and is the fastest loop for
iterating. `--server cbs` runs against a real Couchbase Server, which is slower to set up but
exercises code paths rosmar can't (bucket management, backup/restore, N1QL, XATTRs, Couchbase
Cloud REST APIs) — tests gated on `using_rosmar` are skipped or behave differently under
rosmar, so `cbs` covers more of the test suite. For `--server cbs` you either point at a
Couchbase Server you already have running (`--connstr`) or have `start_local.py` spin one up
for you locally (`--start-cbs`) — see [Couchbase Server for `--server cbs`](#couchbase-server-for---server-cbs) below.

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

## Couchbase Server for `--server cbs`

`--server cbs` needs a Couchbase Server to point Sync Gateway at. Two ways to get one:

- **`--connstr couchbase://<host>`** — use a Couchbase Server you already have running
  (locally, in Docker, on a VM, whatever). This is the only option if you don't have
  Docker/Go available locally.
- **`--start-cbs`** — have `start_local.py` start (or reuse) a local single-node cluster for
  you, via the Sync Gateway checkout's
  [`integration-test/start_cbs.py`](https://github.com/couchbase/sync_gateway/blob/main/integration-test/start_cbs.py),
  which drives [`cbdinocluster`](https://github.com/couchbaselabs/cbdinocluster) to deploy a
  Couchbase Server container. Requires Docker and Go on `PATH`; `cbdinocluster` itself is
  fetched automatically via `go run`. The script lives in the Sync Gateway repo, so
  `--repo-path`/`--git-tag` is required even with `--skip-sync-gateway-build`, and the
  checkout needs to be recent enough to contain that script — if it's missing, use a newer
  `--git-tag`/`--repo-path`.

```bash
uv run environment/local/start_local.py --server cbs --git-tag main --start-cbs
```

`--start-cbs` and `--connstr` are mutually exclusive — pick one. `--start-cbs` always uses
`cbdinocluster`'s fixed `Administrator`/`password` credentials (`--admin-user`/
`--admin-password` aren't configurable in this mode). Re-running with `--start-cbs` reuses the
previously started cluster if it's still up, tracked via
`environment/local/.cbdinocluster-sg-cluster-id` (gitignored). To tear the cluster down or
manage it directly, use `cbdinocluster`
(`go run github.com/couchbaselabs/cbdinocluster@latest rm <cluster-id>`) — `start_local.py` has
no `--stop-cbs` equivalent to `--stop-sync-gateway`.

## Multiple Sync Gateway instances

`--sync-gateways N` starts N Sync Gateway instances against the same backing store, for tests
marked `min_sync_gateways(N)`:

```bash
uv run environment/local/start_local.py --server cbs --connstr couchbase://127.0.0.1 --sync-gateways 2
```

Instances are numbered from 1 and take a *port block* each — Sync Gateway's default ports shifted
by a multiple of 10 — so the usual run puts instance 1 on 4984/4985/4986, instance 2 on
4994/4995/4996 and instance 3 on 5004/5005/5006. Every file belonging to an instance is named
`sync_gateway_instanceN` — its generated config (gitignored) and its log:

| Instance | Public / admin / metrics | Config | Log |
|----------|--------------------------|--------|-----|
| 1 | 4984 / 4985 / 4986 | `sync_gateway_config/sync_gateway_instance1_*.json` | `sync_gateway_instance1.log` |
| 2 | 4994 / 4995 / 4996 | `sync_gateway_config/sync_gateway_instance2_*.json` | `sync_gateway_instance2.log` |
| 3 | 5004 / 5005 / 5006 | `sync_gateway_config/sync_gateway_instance3_*.json` | `sync_gateway_instance3.log` |

A block already in use is skipped and the instance takes the next free one, which it reports as it
starts:

```
Skipping ports 4984-4986: 4984, 4985 already in use
Sync Gateway instance 1/3: public 4994, admin 4995, log sync_gateway_instance1.log
```

Something else on 4984 is usually a Sync Gateway from a second checkout of this repo, which
`--stop-sync-gateway` deliberately leaves alone. Binding the port regardless would fail inside that
instance's log while the script reported success, so it steps aside instead. The instances started
by the *previous* run of this script are stopped before ports are picked, so a plain re-run
reclaims the same ports rather than climbing the range.

The generated topology config lists every instance with the ports it actually got, so the test
framework follows the instances wherever they landed.

Starting Sync Gateway wipes the previous run's logs and generated configs first, so nothing is
left over from a run that used more instances than the current one — a stale
`sync_gateway_instance3.log` next to a two-instance run would just be something to misread.

`N > 1` requires `--server cbs`: rosmar keeps its bucket in the process's own memory, so
separate instances would share no data.

`--stop-sync-gateway` stops every instance started from this checkout — matched on the executable
path, so a system-installed Sync Gateway or one run from another checkout is left alone — and waits
for each to release its ports before returning.

`--skip-sync-gateway-start` describes whatever is already listening rather than whatever
`--sync-gateways` says, since a run that starts nothing cannot know how many are up. It reads the
ports back out of the previous run's generated instance configs and keeps the instances whose admin
port answers. Passing `--sync-gateways` alongside it is an error unless the two agree.

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

- **Logs:** Written to `environment/local/sync_gateway_instanceN.log`, one per instance
  (`sync_gateway_instance1.log` for a single-instance run). Wiped at the start of each run.
- **Configuration:**
  - `--server rosmar`: uses `environment/local/sync_gateway_config/basic_sync_gateway_rosmar.json`
  - `--server cbs`: uses `environment/local/sync_gateway_config/basic_sync_gateway_cbs.json` (with `bootstrap.server` overridden by `--connstr`/`--start-cbs`, if given)

By default this downloads a prebuilt test server. To build it from source
instead, pass `--build-testserver` with a version string:

```bash
uv run environment/local/start_local.py --server rosmar --repo-path /path/to/sync-gateway --build-testserver 4.0.3
```

## Running Tests

After starting the environment, run tests against the config path `start_local.py` wrote to
`environment/local/topology_config` — not the static `topology_configs/*.json` templates
directly, since those don't reflect a `--connstr`/`--start-cbs` override:

```bash
cd tests/dev_e2e
uv run pytest --config "$(cat ../../environment/local/topology_config)"
```
