# JS Docker E2E Session Context

Handoff for new chats. Date: **2026-08-24**. Branch: **`js-test`**.
Repo: `/Users/jayant.dhingra/Desktop/couchbase-lite-tests`.

## What this session is about

Local JavaScript Couchbase Lite TDK work:

1. Docker CBS + SG backend, JS TDK server, run `tests/dev_e2e` against **Sync Gateway**.
2. Add **local Edge Server 1.2.0-4** (HTTP / `ws://` only — JS/browser CBL cannot use HTTPS/WSS).
3. Run JWT + JS→ES smoke against that ES.
4. Re-run the same SG e2e files against ES via `--cbl-remote=es`.

Nothing in this chat was committed unless the user later asked.

## Current environment (left running)

Do **not** stop CBS / SG / ES / JS unless asked.

| Service | How | URL / ports | Notes |
|---|---|---|---|
| Couchbase Server | `docker-cbl-test-cbs-1` | `http://localhost:8091` | Admin `Administrator` / `password`. Query ping `:8093`. |
| Sync Gateway | `docker-cbl-test-sg-1` | `http://localhost:4984` (public), `:4985` (admin) | HTTP, **not TLS**. Admin REST `admin` / `password`. CORS allows `http://localhost:5173`. |
| LogSlurp | `docker-cbl-test-logslurp-1` | `:8180` | Started with compose; not required by this config. |
| Edge Server 1.2.0-4 | `cbl-test-es` (`linux/amd64` deb) | `http://localhost:59840`, shell2http `:20001` | HTTP only (no TLS). CORS allows `http://localhost:5173`. Admin `admin_user` / `password`. Also `user1` / `user2` / `user3` with password `pass` (admin role). |
| JS TDK test server | `npm run dev` in `servers/javascript` | `http://localhost:5173` | Vite. Transport is **WebSocket**, not HTTP. `GET /` may return 404; that is OK if Vite is listening. |

Compose dir: `environment/docker/`.
`docker-compose.override.yml` forces `SSL: "false"` so cbltest can talk to SG without the AWS CA bundle.

Do **not** start a second Vite on 5173. Earlier, `couchbase-lite-js` (sibling repo `~/Desktop/couchbase-lite-js`) was occupying 5173; that is **not** the TDK server. The TDK server is `servers/javascript`.

A leftover standalone container `cbl-sgw` (`couchbase/sync-gateway:3.2.7-enterprise`) was stopped because it held 4984/4985.

latestbuilds `1.2.0/4` has **amd64** deb/rpm only (no linux arm64). This Mac is arm64 → Docker `platform: linux/amd64` + `couchbase-edge-server_1.2.0-4_amd64.deb`. Local checkout `/Users/jayant.dhingra/Desktop/edge-server-main` is **config/CORS/JWT reference only** — do not compile (LiteCore + EE submodules missing).

`start_environment.py` is a false ready-check (matches any historical `"Sync Gateway is up"` log). Always poll CBS `:8091`, query `:8093`, SG `:4984`, admin `:4985`, ES `:59840`.

Rebuild ES only: `docker compose up -d --no-deps --build cbl-test-es`. Without `--no-deps`, compose rebuilds CBS/SG.

## Config

`tests/dev_e2e/config.docker-js.json`:

```json
{
  "test-servers": [{ "url": "http://localhost:5173", "transport": "ws" }],
  "sync-gateways": [{ "hostname": "localhost", "tls": false }],
  "couchbase-servers": [{ "hostname": "localhost" }],
  "edge-servers": [{
    "hostname": "localhost",
    "admin_user": "admin_user",
    "admin_password": "password",
    "config_path": "environment/docker/es/config.json"
  }]
}
```

- Non-absolute `edge-servers[].config_path` is resolved against repo root (`client/src/cbltest/configparser.py`).
- Default ES config (`environment/docker/es/config.json`): HTTP `:59840`, `enable_anonymous_users`, CORS `http://localhost:5173`, empty `db` with `create: true` + client sync.
- `start-edgeserver.sh` rewrites `localhost`/`127.0.0.1` → `cbl-test-sg` in replications and drops `pinned_cert` on `ws://`. jq must tolerate missing `.replications` (default config has none).
- `reset-db.sh` unzips `/home/ec2-user/database/{name}.cblite2.zip` if present; otherwise leaves an empty DB. Local Docker has **no** travel zip — JWT/ES dataset configs must `"create": true` and declare collections.

## How to run

```bash
# Backend
cd environment/docker
docker compose up -d
# poll CBS 8091, query 8093, SG 4984, SG admin 4985, ES 59840

# JS test server
cd servers/javascript
npm run dev   # Vite on :5173

# 1) SG remote (default) — 78 passed / 25 skipped
cd tests/dev_e2e
uv run pytest -v --tb=short --config config.docker-js.json

# 2) JWT + JS→ES smoke (real SG + real ES, no --cbl-remote)
uv run pytest -v --tb=short --config config.docker-js.json test_edge_server_cbl.py edge_server/

# 3) Same SG e2e files, CBL replicates to ES
uv run pytest -v --tb=short --config config.docker-js.json --cbl-remote=es \
  test_basic_replication.py test_query_consistency.py \
  test_replication_behavior.py test_replication_filter.py
```

`--cbl-remote=es` (default `sgw`) is defined in `tests/dev_e2e/conftest.py`. It must **not** be used for `edge_server/` JWT tests — those need the real Sync Gateway object.

## Test results

### 1) Sync Gateway remote (default, no flag)

**78 passed, 25 skipped, 0 real failures** out of 103 collected.

The first full run hung when SG wedged creating GSI indexes after `configure_dataset` bucket recreate. After **CBS+SG restart**, remaining tests passed. Connection-reset failures were that hang, not product bugs.

#### Passed against SG (78)

- `test_basic_replication.py` — 12/12
- `test_custom_conflict.py` — 4/4
- `test_fest.py` — 7/7
- `test_query_consistency.py` — 34/34
- `test_replication_auto_purge.py` — 13/13
- `test_replication_behavior.py` — 1
- `test_replication_blob.py` — `test_blob_replication`
- `test_replication_filter.py` — 6/6

#### Skipped on SG (25) — topology / platform

- 6 Edge Server JWT tests (until local ES existed)
- `test_encrypted_properties.py::test_encrypted_push`
- 2 multipeer
- `test_replication_blob.py::test_pull_non_blob_changes_with_delta_sync_and_compact` (not JS)
- 13 SGW upgrade
- 2 XDCR (need 2 SG + 2 CBS + LB)

### 2) JWT + JS→ES smoke (no `--cbl-remote`)

**7 passed**

- `test_edge_server_cbl.py::test_js_push_to_edge_server_over_ws` — JS CBL push 3 docs to `ws://localhost:59840/db`, no pinned cert
- `edge_server/test_jwt_simple.py` — inline JWT; ES pulls from SG over `ws://`; expected_min docs **5** (zip optional)
- `edge_server/test_jwt_rotation.py` — 5 tests (file JWT, rotation, 401, corrupt file, valid→invalid→valid)

JWT simple first failed with `collection travel.airlines is not found` because empty `create: true` DBs only have `_default._default`. Fix: declare collections on the ES database + `prepare_es_replication_for_sgw` copies replication collections onto the target DB. JWT JSON configs have `"create": true`. Rotation seeds a few docs per collection when `dataset/sg/travel-sg.json` is missing (the 3MB file **does** exist locally; the seed is a fallback).

JWT uses `sync_gateway.scheme` (`http://` locally, `https://` on AWS). `prepare_es_replication_for_sgw` sets the live SG URL and drops `pinned_cert` when SG is HTTP.

### 3) SG e2e files against Edge Server (`--cbl-remote=es`)

**46 passed, 7 skipped** on:

`test_basic_replication.py` + `test_query_consistency.py` + `test_replication_behavior.py` + `test_replication_filter.py`

That is the same 78-test SG set, minus suites that cannot work on ES (see matrix).

| SG suite (count) | Against ES |
|---|---|
| Query consistency (34) | **34 passed** — CBL SQL++ compared to ES adhoc query, not CBS |
| Basic replication (12) | **10 passed**; skip checkpoint reset (ES has no `_purge`) |
| Behavior (1) | **1 passed** |
| Filters (6) | **1 passed** (`test_custom_push_filter`); 5 skipped |
| Fest (7) | Skipped — JS hung (`updateDatabase` `-1`) with two continuous replicators; also needs SG roles/channels |
| Custom conflict (4) | Skipped — replicator never reaches `STOPPED` |
| Auto-purge (13) | Skipped — SG channel/ACL only |
| Blob (1) | Skipped — JS `/updateDatabase` returned `-1` |

**46 + 7 skipped in-file + 25 not collected in that command = the original 78.**

#### How `--cbl-remote=es` works

`tests/dev_e2e/es_remote.py` + autouse fixture in `conftest.py`:

- Replaces `cblpytest.sync_gateways[0]` with `EsRemote` (duck-types SG: `replication_url`, `tls_cert`→None, `get_all_documents`, `get_document`, `update_documents`, `delete_document`, no-op `add_user`/`add_role`).
- Monkeypatches `CouchbaseCloud.configure_dataset` to start ES with `{name}` DB + collections from `{name}-sg-config.json` and load `{name}-sg.json` via `_bulk_docs` (same dataset as SG).
- Skip lists live in `ES_SKIP_FILES` / `ES_SKIP_TEST_NAMES` in `es_remote.py`.
- `EsRemote.close()` closes the original Sync Gateway sessions.

Query consistency (`_query_remote`): when the remote has `_edge`, POST the **CBL** SQL++ to `/travel.travel.{collection}/_query`. Working example:

```text
POST /travel.travel.airlines/_query
{"query":"SELECT meta().id FROM travel.airlines WHERE meta().id NOT LIKE \"_sync%\" ORDER BY id LIMIT 3"}
```

`POST /travel/_query` returns 404 (no such collection). Joins work on any collection keyspace in that DB (`FROM travel.routes JOIN travel.airlines`).

Isolated failures that caused skips (not cascade):

- `_purge` → 404 (checkpoint tests)
- Custom conflict / document-id filter / custom pull filter → `CblTimeoutError` waiting for `STOPPED`
- Blob + fest create → JS TDK `POST /updateDatabase` returned `-1` (server wedged ~2 min)

These look like JS CBL ↔ ES interop limits, not missing dataset setup.

## ES Docker details

`environment/docker/es/`:

| File | Role |
|---|---|
| `Dockerfile` | Ubuntu 22.04 amd64, ES 1.2.0-4 deb, shell2http |
| `config.json` | HTTP listener, CORS, empty `db` |
| `users.json` | Schema stub; `start.sh` / `--add-user` adds bcrypt users (JSON5 with `//` comment — `jq` cannot parse it raw) |
| `start.sh` | Creates `admin_user`/`password`, `user1`/`user2`/`user3`/`pass`; starts shell2http + ES |
| `start-edgeserver.sh` | Writes POSTed config; rewrites SG host; optional replications |
| `reset-db.sh` | Delete `{filename}.cblite2`; unzip sibling zip if present |
| `write-file.sh` | JWT rotation writes `/home/ec2-user/cert/jwt.txt` |
| `add-user.sh` / `kill-edgeserver.sh` / `common.sh` | shell2http handlers |

Compose service `cbl-test-es` ports **59840** and **20001**, `depends_on` SG.

Users were added on the running container with `couchbase-edge-server --add-user …` then `docker compose restart cbl-test-es`. `start.sh` now creates them on boot after an image rebuild.

## Known Docker/SG failure mode

**Symptom:** SG `:4984` and `:4985` time out. Process is still up but HTTP is dead.

**Cause:** `configure_dataset()` deletes/recreates CBS buckets. SG creates GSI indexes and CBS indexer returns `Bucket does not exist or temporarily unavailable for creating new index`. SG retries forever.

**Recovery:**

```bash
docker compose restart cbl-test-cbs cbl-test-sg   # from environment/docker
# Poll CBS 8091 + query 8093 + SG 4984 + SG admin 4985 + ES 59840
```

Restarting SG alone is not enough if the indexer is wedged — restart **CBS and SG**.

`--cbl-remote=es` does **not** recreate CBS buckets (configure_dataset is patched), so this hang should not happen during the ES e2e run.

Docker README: backend no longer officially supported; 8G RAM / 80G disk recommended.

## WIP on branch `js-test` (not committed by this chat)

### Docker backend

`environment/docker/**` — CBS 7.6.4, SG 3.2.0, ES 1.2.0-4, LogSlurp. Override `SSL=false`. SG CORS includes `http://localhost:5173`.

### JS test server

- `servers/javascript/package.json`: `@couchbase/lite-js@1.1.0-5`; `@logtape/logtape`
- `servers/javascript/.npmrc` (untracked): `@couchbase:registry=https://proget.sc.couchbase.com/npm/cbl-npm/`

### Framework / tests

- `client/src/cbltest/configparser.py` — relative ES `config_path` vs repo root
- `tests/dev_e2e/config.docker-js.json` — JS + SG HTTP + CBS + ES
- `tests/dev_e2e/es_ws.py` — `prepare_es_replication_for_sgw`, `assert_http_only_es_config`, `js_edge_replicator_url`
- `tests/dev_e2e/es_remote.py` — `EsRemote` + skip lists + `install_es_remote`
- `tests/dev_e2e/conftest.py` — `--cbl-remote` + skip hook + autouse installer
- `tests/dev_e2e/test_query_consistency.py` — `_query_remote` (ES adhoc vs CBS)
- `tests/dev_e2e/test_edge_server_cbl.py` — JS `ws://` smoke
- `tests/dev_e2e/edge_server/test_jwt_*.py` + JWT JSON configs — TLS-aware, `create: true`, collections
- `tests/dev_e2e/test_fest.py` — f-string assertion fixes (SG run)

Do **not** re-point `test_basic_replication.py` at ES permanently. Default remains SG; ES is `--cbl-remote=es` only.

## Status / health commands

```bash
docker compose -f environment/docker/docker-compose.yml ps
curl -sS -m 5 -o /dev/null -w "CBS %{http_code}\n" http://localhost:8091/ui/index.html
curl -sS -m 5 -o /dev/null -w "SG %{http_code}\n" http://localhost:4984/
curl -sS -m 5 -o /dev/null -w "SGadmin %{http_code}\n" -u admin:password http://localhost:4985/_all_dbs
curl -sS -m 5 -o /dev/null -w "ES %{http_code}\n" http://localhost:59840/
curl -sS -m 5 -o /dev/null -w "ES-user1 %{http_code}\n" -u user1:pass http://localhost:59840/
lsof -i :5173 -sTCP:LISTEN
```

## Do not do

- Do not use AWS `start_backend.py` for this local JS loop.
- Do not hand-edit generated `tests/dev_e2e/config.json` (`config.docker-js.json` is the intentional exception).
- Do not compile `edge-server-main` (missing submodules).
- Do not run `tests/QE/edge_server/` this pass unless asked.
- Do not create extra markdown changelogs; this file is the session handoff.
- Do not commit secrets, certs, or Terraform state.
- Do not kill CBS/SG/ES/JS unless asked.
- Do not commit unless asked.

Per-test SG vs ES table (every nodeid, grouped): [`.cursor/js-e2e-test-matrix.md`](js-e2e-test-matrix.md).

**Skipped-test verdict (docs + lite-js 1.1.0-5, 2026-08-24):** extra Docker will **not** unskip the remaining 19 JS tests. JWT/ES 7 already run. Multipeer / encrypted-properties / blob-compact / upgrade / XDCR are JS product or CBL-version gates. ES-only skips (channels, `_purge`, fest, conflict hang) need SG features ES 1.2 does not have. Official JS 1.0 docs are stale on “no Edge Server” and “SG ≥ 3.3.1” (78 tests passed on SG 3.2.0; ES 1.1 CORS is why JS→ES works). Do not add a second CBS/SG/JS peer unless switching to a native CBL server.

## Related paths

| Path | Role |
|---|---|
| `servers/javascript/` | JS TDK test server (Vite + WebSocket) |
| `client/src/cbltest/websocket_router.py` | Client WS transport for JS |
| `client/src/cbltest/configparser.py` | ES config path resolution |
| `tests/dev_e2e/` | Developer E2E suite |
| `tests/dev_e2e/es_ws.py` | TLS-aware ES↔SG helpers |
| `tests/dev_e2e/es_remote.py` | ES-as-SG adapter for `--cbl-remote=es` |
| `tests/dev_e2e/config.docker-js.json` | Local JS + Docker topology |
| `environment/docker/` | Local CBS + SG + ES + LogSlurp |
| `environment/docker/es/` | Edge Server 1.2.0-4 image |
| `environment/docker/start_environment.py` | Compose up + **unreliable** SG-ready wait |
| `dataset/sg/` | `{name}-sg.json` + `{name}-sg-config.json` (travel-sg.json is ~3MB, present) |
| `.cursor/js-e2e-test-matrix.md` | Every dev_e2e test: SG vs ES Pass/Fail/Skip + reason |
