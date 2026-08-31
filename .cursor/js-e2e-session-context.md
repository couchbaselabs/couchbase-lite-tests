# JS Docker E2E + dev_e2e Catalog — Session Handoff

**Give this file to a new chat** to continue catalog / harness work without re-discovering context.

- **Updated:** 2026-08-31
- **Repo:** `/Users/jayant.dhingra/Desktop/couchbase-lite-tests`
- **Branch:** likely `js-test` (verify with `git branch`)
- **Nothing committed unless user explicitly asked**

---

## What we are building

1. **JS dev_e2e against Docker** — CBS + SG + ES + JS TDK (`servers/javascript`, `@couchbase/lite-js@1.1.0-7`).
2. **`--cbl-remote=es`** — run SG-targeted tests with Edge Server as the CBL replicator remote (`EsRemote` adapter).
3. **HTML test catalog** — `tests/dev_e2e/dev-e2e-test-catalog.html` with **Sync Gateway** and **Edge Server** columns, N/A badges, and reasons.
4. **Harness alignment** — pytest skips, catalog N/A sets, and skip reasons share one source of truth in `es_remote.py`.

Read also: `.cursor/rules/js-e2e-session.mdc` (must-know shortcuts), `environment/docker/es/js-cbl-e2e-interop-report.html` (interop proofs).

---

## Environment (local Docker + JS TDK)

Do **not** stop CBS / SG / ES / JS unless asked.

| Service | Port(s) | Notes |
|---------|---------|-------|
| Couchbase Server | `:8091`, query `:8093` | Admin `Administrator` / `password` |
| Sync Gateway | `:4984`, admin `:4985` | **HTTP** (`tls: false` in config) |
| Edge Server 1.2 | `:59840`, shell2http `:20001` | **HTTP / ws:// only** — JS cannot use HTTPS/WSS |
| JS TDK | `:5173` WebSocket | `servers/javascript` → `npm run dev` (**not** sibling `couchbase-lite-js` Vite) |

Config: `tests/dev_e2e/config.docker-js.json`

```bash
cd environment/docker && docker compose up -d
# Poll: CBS 8091, query 8093, SG 4984, SG admin 4985, ES 59840
cd servers/javascript && npm run dev
```

Rebuild ES only: `docker compose up -d --no-deps --build cbl-test-es`

**SG wedge after bucket recreate:** restart **CBS and SG**, then rerun tests.

---

## Core commands

```bash
# SG (default)
cd tests/dev_e2e
uv run pytest -v --config config.docker-js.json

# ES remote (same tests, EsRemote adapter)
uv run pytest -v --config config.docker-js.json --cbl-remote=es

# Run without ES skips (prove N/A reasons — expect failures/timeouts)
uv run pytest test_replication_filter.py::TestReplicationFilter::test_pull_channels_filter \
  -v --config config.docker-js.json --cbl-remote=es --investigate-es-hangs

# Regenerate catalog (merge into dev-e2e-test-results.json)
uv run python tests/dev_e2e/generate_test_catalog_html.py
uv run python tests/dev_e2e/generate_test_catalog_html.py --run-files test_replication_filter.py
```

**Do not** use `--cbl-remote=es` on `edge_server/` JWT tests — they need real SG.

---

## Catalog badge semantics

| Badge | Meaning |
|-------|---------|
| **N/A** | Test does not target this remote by design. Catalog overrides stored SKIPPED/FAILED via `remote_applicable()` in `generate_test_catalog_html.py`. |
| **Skipped** | Pytest skip fired. Catalog may still show **N/A** if test is in `*_NA_*` sets. |
| **Passed / Failed** | Test actually ran against that remote. |

---

## Key files

| Path | Role |
|------|------|
| `tests/dev_e2e/generate_test_catalog_html.py` | Catalog generator; N/A sets, reasons, HTML output |
| `tests/dev_e2e/dev-e2e-test-catalog.html` | Generated catalog (open in browser) |
| `tests/dev_e2e/dev-e2e-test-results.json` | Persisted SG/ES/es2 run outcomes |
| `tests/dev_e2e/es_remote.py` | `EsRemote` adapter + **shared skip/N/A reasons** |
| `tests/dev_e2e/conftest.py` | `--cbl-remote`, `--investigate-es-hangs`, skip injection |
| `tests/dev_e2e/config.docker-js.json` | Topology + `es-remote.skip-files` / `skip-tests` |
| `tests/dev_e2e/es_ws.py` | ws:// URLs, JWT/ES config prep, drops `pinned_cert` for HTTP |
| `environment/docker/es/js-cbl-e2e-interop-report.html` | SG vs ES interop evidence |
| `environment/docker/es/comparison-logs/es-full.log` | Full ES run log (Aug 27) |
| `.cursor/js-e2e-test-matrix.md` | Per-test SG vs ES matrix (may be stale vs catalog) |

---

## ES skip / N/A single source of truth (`es_remote.py`)

```python
ES_NA_TEST_REASONS  # per-test pytest skip + catalog N/A reason
ES_NA_FILE_REASONS  # per-file (fest, auto_purge)
es_skip_reason_for_test(base)
es_skip_reason_for_file(file_name)
load_es_remote_skips(config)  # from config.docker-js.json es-remote section
```

`conftest.py` uses these for `--cbl-remote=es` skips.  
`generate_test_catalog_html.py` imports `ES_NA_TEST_REASONS` / `ES_NA_FILE_REASONS` for catalog + `fill_missing_reasons()`.

### `config.docker-js.json` → `es-remote`

**skip-files:** fest, auto_purge, upgrade, xdcr, multipeer, encrypted, edge_server_cbl  
**skip-tests:** `test_pull_channels_filter`, `test_replicate_public_channel`, `test_reset_checkpoint_push`, `test_blob_replication`

---

## Catalog generator N/A sets (`generate_test_catalog_html.py`)

| Set | Scope |
|-----|-------|
| `BOTH_NA_FILES` | multipeer — no remote |
| `BOTH_NA_FILES_JS` | encrypted, upgrade, xdcr — JS platform |
| `BOTH_NA_TEST_BASES` | delta blob compact (CBSE-14861), pull resurrected (CBL-7841) |
| `SG_NA_FILES` | JWT / ES smoke tests |
| `ES_NA_FILES` | fest, auto_purge (whole files) |
| `ES_NA_TEST_BASES` | channels filter, public channel, checkpoint push purge, blob `_attachments` |
| `CATALOG_TAIL_ORDER` | encrypted + multipeer collapsed at bottom |

`TEST_CATALOG_NOTES` — visible notes in catalog for tests where SG/ES differ by design (blob, channels, checkpoint, etc.).

---

## Latest catalog snapshot (Aug 31 — verify after regen)

Summary line in HTML may show **72 SG passed / 61 ES passed** — **SG rows for `test_replication_filter.py` can be stale** if last `--run-files` run hit a bad SG fixture (`_es_replicator_idle_terminal`). Live pytest (Aug 31) showed **4 passed + 2 skipped on ES**, **6 passed on SG** for that file.

### Suites fully analyzed in recent chat

#### `test_replication_filter.py` (6 tests)

| Test | SG | ES | Notes |
|------|----|----|-------|
| `test_push_document_ids_filter` | Pass | Pass | CBL `documentIDs` filter |
| `test_pull_document_ids_filter` | Pass | Pass | CBL `documentIDs` filter |
| `test_pull_channels_filter` | Pass | **N/A** | SG channel pull filter |
| `test_replicate_public_channel` | Pass | **N/A** | SG public channel `!` |
| `test_custom_push_filter` | Pass | Pass | CBL-side push filter |
| `test_custom_pull_filter` | Pass | Pass | CBL-side pull filter |

**ES N/A proofs — `test_pull_channels_filter`**

- Test uses `ReplicatorCollectionEntry(..., channels=["United Kingdom", "France"])` — SG sync channels, not document IDs.
- `dataset/sg/travel-sg.json` docs have `"channels": [...]`; `travel-sg-config.json` sync functions call `channel(doc.channels)`.
- `EsRemote.add_user`: *"ES has no SG channel ACL"*.
- Interop report Part 7: *ES 1.2 ACL is collection read/write only*.
- Without skip (`--investigate-es-hangs`): **`CblTimeoutError: Timeout waiting for replicator status`** (~34s, Aug 31 live run).
- Log: `environment/docker/es/comparison-logs/es-full.log` line ~21760.

**ES N/A proofs — `test_replicate_public_channel`**

- Publishes doc with `"channels": ["!"]`; pulls as **user2** who has **empty** `collection_access` in `names-sg-config.json` → only public-channel doc visible on SG.
- Without skip: **`AssertionError: Invalid number of documents after pull`** — **101 == 1** (`dev-e2e-test-results.json` `es2`, `es-full.log` ~21889).
- ES loads full `names` dataset; no channel gate for user2.

#### `test_replication_blob.py`

| Test | SG | ES |
|------|----|----|
| `test_pull_non_blob_changes_with_delta_sync_and_compact` | **N/A both** | **N/A both** | CBSE-14861, JS platform skip |
| `test_blob_replication` | Pass | **N/A** | Push OK on ES; step 7 asserts SG `_attachments` stub |

#### `test_replication_behavior.py`

| Test | SG | ES |
|------|----|----|
| `test_pull_resurrected_doc` | **N/A both** | **N/A both** | CBL-7841; `skip_if_cbl_not(..., ">= 4.2.0")`; not lite-js 1.x |

#### Tail (both remotes N/A on JS catalog)

- `test_encrypted_properties.py` — C TDK only
- `test_basic_multipeer.py` — P2P, last in catalog

#### ES file skips (N/A all tests in file)

- `test_fest.py` — SG roles, channels, sync functions (SG: 78 passed after flaky `test_unshare_list` fixed)
- `test_replication_auto_purge.py` — SG channels, roles, access revocation

---

## `--cbl-remote=es` mechanics (short)

1. `conftest.py` autouse fixture calls `install_es_remote(cblpytest, dataset_path)`.
2. Replaces `sync_gateways[0]` with `EsRemote` (duck-types SG REST).
3. Patches `configure_dataset` → ES HTTP DB + bulk load from `{name}-sg.json`.
4. `prepare_es_replication_for_sgw` rewrites SG URL to HTTP, drops `pinned_cert`.

Query consistency (34 tests): ES adhoc query via `_query_remote`, not CBS — **all pass on ES**.

---

## Interop vs N/A (important distinction)

| Category | Example | Catalog treatment |
|----------|---------|-------------------|
| **N/A by design** | SG channels, `_purge`, `_attachments` shape | N/A badge + specific reason |
| **Interop failure** | doc-ID filter second push IDLE hang (older es-full) | Was Failed; some now Pass on current lite-js |
| **JS product gap** | multipeer, encrypted, CBL ≥ 4.0 upgrade | N/A both remotes |

See `js-cbl-e2e-interop-report.html` Part 5 (8 interop failures) and Part 7 (expected skips).

---

## Harness changes made (Aug 31, uncommitted)

1. **`es_remote.py`** — `ES_NA_TEST_REASONS`, `ES_NA_FILE_REASONS`, `es_skip_reason_for_test/file()`.
2. **`conftest.py`** — per-test/file skip reasons (not generic "channels/roles/CBS" for everything).
3. **`generate_test_catalog_html.py`** — imports shared reasons; `TEST_CATALOG_NOTES` for blob, channels, resurrected, etc.; `test_blob_replication` in `ES_NA_TEST_BASES`.
4. **`test_replication_behavior.py`** — `test_pull_resurrected_doc` kept at `skip_if_cbl_not >= 4.2.0` (product gap → N/A, not Failed).

---

## Regenerate catalog cleanly

```bash
cd /Users/jayant.dhingra/Desktop/couchbase-lite-tests

# Full regen from stored results (no pytest)
uv run python tests/dev_e2e/generate_test_catalog_html.py

# Refresh one file on both remotes (fixes stale SG rows)
uv run python tests/dev_e2e/generate_test_catalog_html.py --run-files test_replication_filter.py
```

If SG runs fail with `ValueError: _es_replicator_idle_terminal did not yield a value`, fix env/fixture before trusting SG column — ES column + N/A reasons are still valid.

---

## Do not do

- Do not commit unless user asks.
- Do not stop CBS/SG/ES/JS unless asked.
- Do not use `--cbl-remote=es` on `edge_server/` JWT tests.
- Do not hand-edit `dev-e2e-test-results.json` without understanding merge logic.
- Do not create extra markdown changelogs — **this file is the handoff**.
- Do not treat ES Failed on channel tests as product bugs — they are N/A (SG-only semantics).

---

## Suggested next steps for a new chat

1. Regenerate catalog after clean SG+ES pytest for any file with stale SG failures.
2. Continue suite-by-suite N/A proof docs (next: `test_basic_replication` checkpoint tests, `test_custom_conflict`).
3. Optionally sync `.cursor/js-e2e-test-matrix.md` with catalog N/A sets.
4. Commit harness + catalog when user asks.

---

## Quick attach prompt for new chat

Copy-paste into a new Cursor chat:

> Read `.cursor/js-e2e-session-context.md` and `.cursor/rules/js-e2e-session.mdc`. Continue JS dev_e2e catalog work: validate N/A classifications, regenerate `dev-e2e-test-catalog.html`, do not commit unless I ask.
