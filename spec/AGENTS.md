# Specifications — `spec/`

Single source of truth for all contracts in the harness: the OpenAPI specification for the test server REST API, markdown test specifications that define expected test behavior, and dataset format documentation. Every other directory (servers, client, tests) consumes these contracts.

## Scope

You own everything under `spec/`:
- `spec/api/api.yaml` — OpenAPI 3.1.0 specification (THE contract for every server)
- `spec/api/conflict-resolvers.md`, `spec/api/replication-filters.md` — supplementary API definitions
- `spec/tests/dev_e2e/` — developer E2E test specs (12 numbered files)
- `spec/tests/QE/` — QA test specs (20 files + 12 edge-server files)
- `spec/dataset/dataset.md`, `spec/dataset/blobs.md` — dataset format docs

You do **not** own server implementations or test code — but your specs define the contracts they follow.

## Layout

```
spec/
├── api/
│   ├── api.yaml                        # OpenAPI 3.1.0 (1504 lines) — THE contract
│   ├── conflict-resolvers.md
│   └── replication-filters.md
│
├── tests/
│   ├── dev_e2e/                        # Numbered test specs (NNN-feature-name.md)
│   │   ├── 001-basic-replication.md
│   │   ├── 002-replication-filter.md
│   │   ├── 003-replication-auto-purge.md
│   │   ├── 004-replication-blob.md
│   │   ├── 005-test-fest.md
│   │   ├── 006-custom-conflict.md
│   │   ├── 007-replication-behavior.md
│   │   ├── 008-query-consistency.md
│   │   ├── 009-encrypted-properties.md
│   │   ├── 010-multipeer.md
│   │   ├── 011-replication-upgrade.md
│   │   └── 012-replication-xdcr.md
│   │
│   └── QE/                             # Test specs matching the test filename
│       ├── test_db_gone.md
│       ├── test_delta_sync.md
│       ├── test_high_availability.md
│       ├── test_large_doc_workloads.md
│       ├── test_log_redaction.md
│       ├── test_multipeer.md
│       ├── test_multiple_servers.md
│       ├── test_no_conflicts.md
│       ├── test_peer_to_peer.md
│       ├── test_peer_to_peer_topology.md
│       ├── test_replication_eventing.md
│       ├── test_replication_functional.md
│       ├── test_replication_multiple_clients.md
│       ├── test_replicator_encryption_hook.md
│       ├── test_rolling_upgrade_sgw.md
│       ├── test_system_multipeer.md
│       ├── test_ttl.md
│       ├── test_upg_sgw.md
│       ├── test_users_channels.md
│       ├── test_xattrs.md
│       └── edge_server/                # Edge Server specs (test_feature_name.md)
│           ├── test_authentication.md
│           ├── test_blobs.md
│           ├── test_changes_feed.md
│           ├── test_chaos_scenarios.md
│           ├── test_crud.md
│           ├── test_database_edge_server.md
│           ├── test_logging.md
│           ├── test_query_edge_server.md
│           ├── test_replication_edge_server.md
│           ├── test_replication_sanity.md
│           ├── test_system.md
│           └── test_ttl_expires.md
│
└── dataset/
    ├── dataset.md                      # Schemas for `travel`, `names`, `posts`, `todo`, `short_expiry`, `upgrade`
    └── blobs.md                        # Blob catalog with SHA-1 digests + sizes
```

## API Specification (`api/api.yaml`)

| Field | Value |
|---|---|
| Format | OpenAPI 3.1.0 |
| Server | `http://{tenant}:8080` (test server on localhost or EC2) |
| Current version | **2.0.3** |
| Required request headers | `CBLTest-API-Version` (int), `CBLTest-Client-ID` (UUID) |
| Required response headers | `CBLTest-API-Version`, `CBLTest-Server-ID` |
| Enum values | **Case-insensitive** (stated in `info.description`) |

### Endpoints (19 total)

`GET /`, `POST /newSession`, `POST /reset`, `POST /getAllDocuments`, `POST /updateDatabase`, `POST /startReplicator`, `POST /stopReplicator`, `POST /getReplicatorStatus`, `POST /snapshotDocuments`, `POST /verifyDocuments`, `POST /performMaintenance`, `POST /runQuery`, `POST /getDocument`, `POST /log`, `POST /startListener`, `POST /stopListener`, `POST /startMultipeerReplicator`, `POST /stopMultipeerReplicator`, `POST /getMultipeerReplicatorStatus`.

### Recent Version History

| Version | Date | Change |
|---|---|---|
| 2.0.3 | 04/17/2026 | Add identity property to `startListener` |
| 2.0.2 | 07/24/2025 | Add peer ID to `startMultipeerReplicator` return |
| 2.0.1 | 07/10/2025 | Add Merge-Dict conflict resolver |
| 2.0.0 | 06/13/2025 | **Breaking**: API version → 2; dataset URLs, blob URLs |
| 1.2.3 | 12/09/2025 | Transport type for multipeer |
| 1.2.2 | 09/19/2025 | Headers property in `ReplicatorConfiguration` |
| 1.2.1 | 06/04/2025 | Authenticator for multipeer |
| 1.2.0 | 04/09/2025 | Multipeer replicator endpoints |
| 1.1.0 | 03/05/2025 | Listener endpoints |
| 1.0.0 | 09/27/2024 | `newSession`, `/log` endpoint |

### Supplementary API Docs

- `conflict-resolvers.md` — predefined resolvers: `local-wins`, `remote-wins`, `null`, `merge`, `delete`, `merge-dict`
- `replication-filters.md` — predefined filters: `documentIDs`, `deleted-only`

## Test Spec Format

```markdown
## #N test_function_name

### Description
What this test verifies.

### Steps
1. Reset SG and load `dataset` dataset.
2. Reset local database, and load `dataset` dataset.
3. Start a replicator:
    * endpoint: `/dataset`
    * collections: `scope.collection`
    * type: push/pull/pushAndPull
    * continuous: true/false
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that [expected outcome].
```

QE specs may omit `## #N` and use just `## test_function_name`.

### Naming Conventions

| Directory | Naming | Example |
|---|---|---|
| `spec/tests/dev_e2e/` | `NNN-feature-name.md` (next: 013) | `001-basic-replication.md` ↔ `test_basic_replication.py` |
| `spec/tests/QE/` | `test_feature_name.md` (matches `.py` filename) | `test_xattrs.md` ↔ `test_xattrs.py` |
| `spec/tests/QE/edge_server/` | `test_feature_name.md` | `test_crud.md` ↔ `tests/QE/edge_server/test_crud.py` |

## Dataset Documentation (`dataset/`)

### `dataset.md`

Schemas for `travel`, `names`, `posts`, `todo`, `short_expiry`, `upgrade`. For each dataset:
- CBL collections with document counts + ID ranges
- SG collections with document counts + ID ranges
- SG config (sync functions, users, roles, channels)
- Special notes (blobs, channel assignments)

### `blobs.md`

Catalog of test blobs with SHA-1 digests and sizes:
- **Small**: s1–s10.jpg (~45–230 KB)
- **Large**: l1–l10.jpg (~1.7–3.2 MB)
- **Extra-large**: xl1.jpg (~21 MB), xl2.jpg (~52 MB)

## Rules

- **API changes go to `api.yaml` FIRST** — then implement in all 5 server platforms + Python framework.
- **Every new test MUST have a corresponding spec** — no orphan tests in `tests/`.
- **Spec files are the single source of truth for test flow** — test methods must not have docstrings or inline comments describing their steps. The numbered steps in the spec (matching `mark_test_step` calls) serve that purpose. Helper functions still get docstrings.
- **dev_e2e specs** — `NNN-feature-name.md` (next number: **013**).
- **QE specs** — match the test filename: `test_feature_name.md`.
- **Edge Server specs** — under `spec/tests/QE/edge_server/`.
- **Enum values in the API spec are case-insensitive** — always note this in the spec.
- **API YAML must pass Redocly lint** before merge.
- **Dataset schema changes** must update `spec/dataset/dataset.md`.
- **New conflict resolvers or replication filters** must be documented in `spec/api/`.
- **Version changelog** lives at the top of `info.description` in `api.yaml`.

## CI Validation

`.github/workflows/openapi.yml` triggers on changes to `spec/api/`:
- **Redocly lint** validates `api.yaml`
- **yamllint** validates YAML formatting under `spec/`
- Posts a Redocly preview link as a PR comment
- Must pass before merge

## Commands

```bash
# Lint OpenAPI spec
npx @redocly/cli lint spec/api/api.yaml

# YAML lint
yamllint spec/

# Preview API docs (Redocly)
npx @redocly/cli preview-docs spec/api/api.yaml
```

## Cross-References

| What | Where | Relationship |
|---|---|---|
| Server implementations | [servers/](../servers/) (c, dotnet, ios, jak, javascript) | Must implement every `api.yaml` endpoint |
| Python framework | [client/src/cbltest/requests.py](../client/src/cbltest/requests.py) | `TestServerRequestType` enum maps to `api.yaml` endpoints |
| Versioned requests/responses | [client/src/cbltest/v1/](../client/src/cbltest/v1/), [v2/](../client/src/cbltest/v2/) | Match `api.yaml` schemas |
| Test suites (dev_e2e) | [tests/dev_e2e/](../tests/dev_e2e/) | Must follow `spec/tests/dev_e2e/` |
| Test suites (QE) | [tests/QE/](../tests/QE/) | Must follow `spec/tests/QE/` |
| Datasets (actual files) | [dataset/sg/](../dataset/sg/), [dataset/server/](../dataset/server/) | Schema documented in `spec/dataset/` |
| CI validation | [.github/workflows/openapi.yml](../.github/workflows/openapi.yml) | Lints `api.yaml` on every PR |
