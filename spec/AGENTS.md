# Agent: Specifications (spec/)

## Identity

You are a specialized agent for the specification layer of the Couchbase Lite System Test
Harness. You maintain the OpenAPI specification that defines the test server REST API, the
markdown test specifications that define expected behavior for every test, and the dataset
format documentation. You are the source of truth that all other agents depend on.

## Scope

You own all files under `spec/`:
- `spec/api/api.yaml` — OpenAPI 3.1.0 specification (THE contract for all server implementations)
- `spec/api/conflict-resolvers.md` — Predefined conflict resolver definitions
- `spec/api/replication-filters.md` — Predefined replication filter definitions
- `spec/tests/dev_e2e/` — Test specifications for developer E2E tests (12 numbered files)
- `spec/tests/QE/` — Test specifications for QA tests (16 files + 12 edge server files)
- `spec/dataset/` — Dataset schema documentation (`dataset.md`, `blobs.md`)

You do NOT own the server implementations or test code, but your specs define the contracts
they must follow.

## API Specification (`api/api.yaml`)

- **Format:** OpenAPI 3.1.0
- **Current version:** 2.0.3
- **Required request headers:** `CBLTest-API-Version` (integer), `CBLTest-Client-ID` (UUID)
- **Response headers:** `CBLTest-API-Version`, `CBLTest-Server-ID`
- **Enum values are case-insensitive** (stated in the spec description)

### Endpoints (19 total)
`GET /`, `POST /newSession`, `POST /reset`, `POST /getAllDocuments`,
`POST /updateDatabase`, `POST /startReplicator`, `POST /stopReplicator`,
`POST /getReplicatorStatus`, `POST /snapshotDocuments`, `POST /verifyDocuments`,
`POST /performMaintenance`, `POST /runQuery`, `POST /getDocument`, `POST /log`,
`POST /startListener`, `POST /stopListener`, `POST /startMultipeerReplicator`,
`POST /stopMultipeerReplicator`, `POST /getMultipeerReplicatorStatus`

### Supplementary API Docs
- `conflict-resolvers.md` — `local-wins`, `remote-wins`, `null`, `merge`, `delete`, `merge-dict`
- `replication-filters.md` — `documentIDs`, `deleted-only`

### CI Validation (GitHub Actions)
- `.github/workflows/openapi.yml` triggers on changes to `spec/api/`
- Runs: Redocly lint, yamllint, and posts preview link on PRs
- Must pass before merge

## Test Specifications

### dev_e2e Specs (`tests/dev_e2e/`)

**Naming convention:** `NNN-feature-name.md` (numbered 001 through 012)

**Spec-to-code mapping:**
| Spec File | Test File | Location |
|-----------|-----------|----------|
| `001-basic-replication.md` | `test_basic_replication.py` | `tests/dev_e2e/` |
| `002-replication-filter.md` | `test_replication_filter.py` | `tests/dev_e2e/` |
| `003-replication-auto-purge.md` | `test_replication_auto_purge.py` | `tests/dev_e2e/` |
| `004-replication-blob.md` | `test_replication_blob.py` | `tests/dev_e2e/` |
| `005-test-fest.md` | `test_fest.py` | `tests/dev_e2e/` |
| `006-custom-conflict.md` | `test_custom_conflict.py` | `tests/dev_e2e/` |
| `007-replication-behavior.md` | `test_replication_behavior.py` | `tests/dev_e2e/` |
| `008-query-consistency.md` | `test_query_consistency.py` | `tests/dev_e2e/` |
| `009-encrypted-properties.md` | `test_encrypted_properties.py` | `tests/dev_e2e/` |
| `010-multipeer.md` | `test_multipeer.py` | `tests/dev_e2e/` |
| `011-replication-upgrade.md` | `test_replication_upgrade.py` | `tests/dev_e2e/` |
| `012-replication-xdcr.md` | `test_replication_xdcr.py` | `tests/dev_e2e/` |

### QE Specs (`tests/QE/`)

**Naming convention:** `test_feature_name.md` (matches the test file name exactly)

Files: `test_db_online_offline.md`, `test_delta_sync.md`, `test_high_availability.md`,
`test_large_doc_workloads.md`, `test_log_redaction.md`, `test_multipeer.md`,
`test_multiple_servers.md`, `test_no_conflicts.md`, `test_peer_to_peer.md`,
`test_peer_to_peer_topology.md`, `test_replication_eventing.md`,
`test_replication_functional.md`, `test_replication_multiple_clients.md`,
`test_replicator_encryption_hook.md`, `test_rolling_upgrade_sgw.md`,
`test_system_multipeer.md`, `test_ttl.md`, `test_upg_sgw.md`,
`test_users_channels.md`, `test_xattrs.md`

### Edge Server Specs (`tests/QE/edge_server/`)

**Naming convention:** `test_feature_name.md` (same as QE)

Files: `test_authentication.md`, `test_blobs.md`, `test_changes_feed.md`,
`test_chaos_scenarios.md`, `test_crud.md`, `test_database_edge_server.md`,
`test_logging.md`, `test_query_edge_server.md`, `test_replication_edge_server.md`,
`test_replication_sanity.md`, `test_system.md`, `test_ttl_expires.md`

### Test Spec Format

Every test in a spec file follows this structure:
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

QE specs may omit the `## #N` numbering and use just `## test_function_name`.

## Dataset Documentation (`dataset/`)

### `dataset.md`
Documents schemas for all datasets: `travel`, `names`, `posts`, `todo`, `short_expiry`, `upgrade`

For each dataset:
- CBL collections with document counts and ID ranges
- SG collections with document counts and ID ranges
- SG config (sync functions, users, roles, channels)
- Special notes (blobs, channel assignments)

### `blobs.md`
Catalog of test blob files with SHA-1 digests and sizes:
- Small: s1–s3.jpg (~45–50KB)
- Large: l1–l10.jpg (~1.7–3.2MB)
- Extra-large: xl1.jpg (~21MB)

## Rules

- **API changes go to `api.yaml` FIRST** — then implement in all 5 platform servers + Python framework
- **Every new test MUST have a corresponding spec** — no orphan tests in `tests/`
- **dev_e2e specs** use numbered format: `NNN-feature-name.md` (next number: 013)
- **QE specs** match test filenames: `test_feature_name.md`
- **Edge server specs** go in `spec/tests/QE/edge_server/`
- **API YAML must pass Redocly lint** — run `npx @redocly/cli lint spec/api/api.yaml`
- **Dataset schema changes** must update `spec/dataset/dataset.md`
- **New conflict resolvers or replication filters** must be documented in `spec/api/`
- **Version changelog** goes at the top of the `info.description` field in `api.yaml`
- **Enum values are case-insensitive** — always note this in the spec

## Commands
```bash
# Lint OpenAPI spec
npx @redocly/cli lint spec/api/api.yaml

# YAML lint (all spec files)
yamllint spec/

# Preview API docs (generates a Redocly page)
npx @redocly/cli preview-docs spec/api/api.yaml
```

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| Server implementations | `servers/{c,dotnet,ios,jak,javascript}/` | Must implement all `api.yaml` endpoints |
| Python framework | `client/src/cbltest/requests.py` | `TestServerRequestType` enum maps to `api.yaml` endpoints |
| Python framework | `client/src/cbltest/v1/`, `v2/` | Request/response classes match `api.yaml` schemas |
| Test suites (dev_e2e) | `tests/dev_e2e/` | Must follow behavior in `spec/tests/dev_e2e/` |
| Test suites (QE) | `tests/QE/` | Must follow behavior in `spec/tests/QE/` |
| Datasets (actual files) | `dataset/sg/`, `dataset/server/` | Schema documented in `spec/dataset/` |
| CI validation | `.github/workflows/openapi.yml` | Lints `api.yaml` on every PR |

