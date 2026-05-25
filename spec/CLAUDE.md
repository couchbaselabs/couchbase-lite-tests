# CLAUDE.md — Specifications (spec/)

## What This Is

This directory is the single source of truth for all contracts and test definitions in the
Couchbase Lite System Test Harness. It contains the OpenAPI specification for the test server
REST API, markdown test specifications that define expected behavior for every test, and
dataset format documentation.

## Directory Structure

```
spec/
├── api/                            # Test Server REST API specification
│   ├── api.yaml                    # OpenAPI 3.1.0 spec (1497 lines) — THE contract
│   ├── conflict-resolvers.md       # Predefined conflict resolver definitions
│   └── replication-filters.md      # Predefined replication filter definitions
│
├── tests/                          # Test specifications (markdown)
│   ├── dev_e2e/                    # Developer E2E test specs (numbered)
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
│   └── QE/                         # QA test specs (named after test files)
│       ├── test_db_online_offline.md
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
│       └── edge_server/            # Edge Server test specs
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
└── dataset/                        # Dataset format documentation
    ├── dataset.md                  # Schema for travel, names, posts, todo, short_expiry, upgrade
    └── blobs.md                    # Blob catalog (small, large, extra-large with digests)
```

## API Specification (`spec/api/api.yaml`)

### Overview
- **Format:** OpenAPI 3.1.0
- **Server:** `http://{tenant}:8080` (test server on localhost or EC2)
- **Current version:** 2.0.2
- **Required headers:** `CBLTest-API-Version` (integer), `CBLTest-Client-ID` (UUID)
- **Response headers:** `CBLTest-API-Version`, `CBLTest-Server-ID`

### Version History (recent)
| Version | Date | Changes |
|---------|------|---------|
| 2.0.2 | 07/24/2025 | Add peer ID to startMultipeerReplicator return |
| 2.0.1 | 07/10/2025 | Add Merge-Dict Conflict Resolver |
| 2.0.0 | 06/13/2025 | **Breaking**: API version → 2, dataset URLs, blob URLs |
| 1.2.3 | 12/09/2025 | Transport type for multipeer |
| 1.2.2 | 09/19/2025 | Headers property in ReplicatorConfiguration |
| 1.2.1 | 06/04/2025 | Authenticator for multipeer |
| 1.2.0 | 04/09/2025 | Multipeer replicator endpoints |
| 1.1.0 | 03/05/2025 | Listener endpoints |
| 1.0.0 | 09/27/2024 | newSession, log endpoint |

### Endpoints Defined
All 17 endpoints that every test server must implement:
`/` (GET), `/newSession`, `/reset`, `/getAllDocuments`, `/updateDatabase`,
`/startReplicator`, `/getReplicatorStatus`, `/snapshotDocuments`, `/verifyDocuments`,
`/performMaintenance`, `/runQuery`, `/getDocument`, `/log`, `/startListener`,
`/stopListener`, `/startMultipeerReplicator`, `/stopMultipeerReplicator`,
`/getMultipeerReplicatorStatus`

### Supplementary API Docs
- **`conflict-resolvers.md`** — Predefined resolvers: `local-wins`, `remote-wins`, `null`,
  `merge`, `delete`, `merge-dict`
- **`replication-filters.md`** — Predefined filters: `documentIDs`, `deleted-only`

## Test Specification Format

### dev_e2e Specs (`spec/tests/dev_e2e/`)

Naming: `NNN-feature-name.md` (numbered 001–012)

Each test in the file follows this structure:
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

### QE Specs (`spec/tests/QE/`)

Naming: `test_feature_name.md` (matches the test file name in `tests/QE/`)

Same numbered-step format, but may be more detailed with edge cases, multi-SGW scenarios,
and cleanup requirements.

### Mapping: Spec → Test File → Test Code

| Spec | Test File | Location |
|------|-----------|----------|
| `spec/tests/dev_e2e/001-basic-replication.md` | `test_basic_replication.py` | `tests/dev_e2e/` |
| `spec/tests/QE/test_xattrs.md` | `test_xattrs.py` | `tests/QE/` |
| `spec/tests/QE/edge_server/test_crud.md` | `test_crud.py` | `tests/QE/edge_server/` |

## Dataset Documentation (`spec/dataset/`)

### `dataset.md`
Documents the schema for all available datasets: `travel`, `names`, `posts`, `todo`,
`short_expiry`, `upgrade`. For each:
- CBL collections with document counts and ID ranges
- SG collections with document counts and ID ranges
- SG config (sync functions, users, roles, channels)
- Special notes (blobs, channel assignments)

### `blobs.md`
Catalog of test blob files with exact digests and sizes:
- Small (s1–s3.jpg, ~45–50KB)
- Large (l1–l10.jpg, ~1.7–3.2MB)
- Extra-large (xl1.jpg, ~21MB)

## CI Validation

### GitHub Actions (`openapi.yml`)
Triggered on changes to `spec/api/`:
- **Redocly lint** — validates `api.yaml` against OpenAPI rules
- **yamllint** — validates YAML formatting for all files under `spec/`
- **PR preview** — posts a Redocly preview link as a PR comment

### Local Validation
```bash
# Lint OpenAPI spec (requires redocly CLI)
npx @redocly/cli lint spec/api/api.yaml

# YAML lint
yamllint spec/
```

## Rules
- **API changes go to `api.yaml` FIRST** — then implementations in all 5 server platforms
- **Every new test MUST have a corresponding spec** — no orphan tests
- **Spec files are the single source of truth for test flow** — test methods should NOT have docstrings or inline comments describing their steps. The numbered steps in the spec (matching `mark_test_step` calls) serve that purpose. Helper functions and utilities should still have docstrings.
- **dev_e2e specs use numbered format**: `NNN-feature-name.md`
- **QE specs match test file names**: `test_feature_name.md`
- **Edge server specs** go in `spec/tests/QE/edge_server/`
- **Enum values in the API spec are case-insensitive** (noted in the spec header)
- **API yaml must pass Redocly lint** before merge
- **Dataset changes** must update `spec/dataset/dataset.md`
- **New conflict resolvers or filters** must be documented in `spec/api/`

## Cross-References

| What | Where | Relationship |
|------|-------|-------------|
| Server implementations | `servers/{c,dotnet,ios,jak,javascript}/` | Must implement all endpoints in `api.yaml` |
| Python framework | `client/src/cbltest/requests.py` | `TestServerRequestType` enum maps to `api.yaml` endpoints |
| Test suites | `tests/dev_e2e/`, `tests/QE/` | Must match behavior defined in `spec/tests/` |
| Datasets (actual files) | `dataset/sg/`, `dataset/server/` | Schema documented in `spec/dataset/` |
| CI validation | `.github/workflows/openapi.yml` | Lints `api.yaml` on every PR |

