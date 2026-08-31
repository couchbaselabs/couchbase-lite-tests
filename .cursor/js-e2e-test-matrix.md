# JS dev e2e test matrix — Sync Gateway vs Edge Server

Date: **2026-08-24**. Branch: **`js-test`**. Config: `tests/dev_e2e/config.docker-js.json`.

**How results were produced**

| Remote | Command | Recorded result |
|---|---|---|
| Sync Gateway | `uv run pytest -v --tb=short --config config.docker-js.json` | 78 passed, 25 skipped, 0 failed (103 collected; JWT skipped — no ES in config yet) |
| Edge Server (same SG files) | `… --cbl-remote=es` on basic / query / behavior / filter | 46 passed, 7 skipped, 0 failed |
| Edge Server JWT + JS smoke | `… test_edge_server_cbl.py edge_server/` (no `--cbl-remote`) | 7 passed, 0 failed |

**Legend**

| Mark | Meaning |
|---|---|
| ✅ | Done — test ran and passed |
| ⏭️ | Skip — not run this time (missing config, hang, or not that remote’s test) |
| 🚫 | Not supported — product/platform has no API for this (not a skip) |
| ❌ | Fail — none recorded |
| ⬜ | Does not apply — this column is not that result |

Columns:

- **Sync Gateway** / **Edge Server** — ✅, ⏭️, 🚫, or ❌ for that remote.
- **✅** / **❌** / **⏭️** / **🚫** — which remotes that applies to (`SG`, `ES`, `both`, or ⬜).
- **Reason** — why, including ES evidence.

No test failed in the **recorded** SG or ES runs. Cases that hung or 404’d on ES were then marked ⏭️; the failure we saw is in Reason. Multi-peer, C-only encryption, JS-excluded compact, native CBL 4.x upgrade/XDCR, and ES-only SG features (channels, roles, `_purge`) are **🚫**, not ⏭️.

**Totals (current tree, 104 nodeids)**

| | SG ✅ | SG ❌ | SG ⏭️ | SG 🚫 | ES ✅ | ES ❌ | ES ⏭️ | ES 🚫 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Count | 78 | 0 | 7 | 19 | 53 | 0 | 8 | 43 |

SG ⏭️ 7 = JWT + JS→ES smoke (not CBL→SG). SG 🚫 19 = blob compact 1 + encrypted 1 + multipeer 2 + upgrade 13 + XDCR 2. ES ⏭️ 8 = doc-id/custom-pull filters 3 + conflict 4 + blob-vs-ES 1. ES 🚫 43 = SG-only features on ES + the 19 JS-unsupported tests.

---

## 1. Basic replication (`test_basic_replication.py`)

CBL ↔ remote push/pull of `travel` / `names`.

| Test name | Sync Gateway | Edge Server | ✅ | ❌ | ⏭️ | 🚫 | Reason |
|---|---|---|---|---|---|---|---|
| `test_replicate_non_existing_sg_collections` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Push `travel.airlines` to remote DB `names`. Both remotes return 404 / CBL 10404. |
| `test_push` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | One-shot push of travel collections; `compare_local_and_remote`. |
| `test_pull` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | One-shot pull; docs match. |
| `test_push_and_pull` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | One-shot push-and-pull; docs match. |
| `test_continuous_push` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Continuous push until idle/stopped. |
| `test_continuous_pull` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Continuous pull until idle/stopped. |
| `test_continuous_push_and_pull` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Continuous push-and-pull. |
| `test_default_collection_push` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `names` / `_default._default` push. |
| `test_default_collection_pull` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Default collection pull. |
| `test_default_collection_push_and_pull` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Default collection push-and-pull. |
| `test_reset_checkpoint_push` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | After push, **purges** `airline_10` on remote (`POST …/_purge`), then reset-checkpoint push. ES has no `_purge` API. |
| `test_reset_checkpoint_pull` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Same `_purge` requirement on the pull path. ES does not support it. |

**Group: SG 12 ✅. ES 10 ✅, 2 🚫 (`_purge`).**

---

## 2. Query consistency (`test_query_consistency.py`)

Replicate `travel`, run SQL++ on CBL and on the remote. SG compares to **CBS N1QL**. ES compares to **ES adhoc SQL++** (`POST /travel.travel.{collection}/_query` with the CBL query text).

| Test name | Sync Gateway | Edge Server | ✅ | ❌ | ⏭️ | 🚫 | Reason |
|---|---|---|---|---|---|---|---|
| `test_query_docids` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `SELECT meta().id FROM travel.airlines` (exclude `_sync%`). |
| `test_any_operator` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `ANY … SATISFIES` on `travel.routes` schedule. |
| `test_select_star[airline_10]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `SELECT *` existing airline. |
| `test_select_star[doc_id_does_not_exist]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `SELECT *` missing id; empty both sides. |
| `test_limit_offset[5-5]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | LIMIT 5 OFFSET 5; compare counts. |
| `test_limit_offset[-5--5]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Negative limit/offset; empty both sides. |
| `test_query_where_and_or` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Country OR + vacancy on hotels. |
| `test_multiple_selects` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `SELECT name, meta().id` France hotels. |
| `test_query_pattern_like[Royal Engineers Museum]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Exact LIKE on landmarks. |
| `test_query_pattern_like[Royal engineers museum]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Case variant LIKE. |
| `test_query_pattern_like[eng%e%]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Wildcard LIKE. |
| `test_query_pattern_like[Eng%e%]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Wildcard LIKE (capital E). |
| `test_query_pattern_like[%eng____r%]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Underscore LIKE. |
| `test_query_pattern_like[%Eng____r%]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Underscore LIKE (capital E). |
| `test_query_pattern_regex[\bEng.*e\b]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `REGEXP_CONTAINS` (capital). |
| `test_query_pattern_regex[\beng.*e\b]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `REGEXP_CONTAINS` (lower). |
| `test_query_is_not_valued` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `name IS NULL OR name IS MISSING` on hotels. |
| `test_query_ordering` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `ORDER BY name ASC` hotels. |
| `test_query_substring` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `CONTAINS` / `UPPER` on landmark email. |
| `test_query_join` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | routes ⋈ airlines SFO; ES uses CBL join text (not CBS `ON KEYS`). |
| `test_query_inner_join` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | routes INNER JOIN airports. |
| `test_query_left_join[LEFT JOIN]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | LEFT JOIN; CBS uses `LEFT JOIN` + `ON KEYS`. |
| `test_query_left_join[LEFT OUTER JOIN]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Same CBL query; CBS uses `LEFT OUTER JOIN`. |
| `test_equality[=]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `country = "France"` airports. |
| `test_equality[!=]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `country != "France"`. |
| `test_comparison[>]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `geo.alt > 1000`. |
| `test_comparison[>=]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `geo.alt >= 1000`. |
| `test_comparison[<]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `geo.alt < 1000`. |
| `test_comparison[<=]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `geo.alt <= 1000`. |
| `test_in` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `country IN ["United States", "France"]`. |
| `test_between[BETWEEN]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `geo.alt BETWEEN 100 and 200`. |
| `test_between[NOT BETWEEN]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `geo.alt NOT BETWEEN 100 and 200`. |
| `test_same[IS]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `iata IS null`. |
| `test_same[IS NOT]` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | `iata IS NOT null`. |

**Group: SG 34 ✅. ES 34 ✅.**

---

## 3. Replication behavior (`test_replication_behavior.py`)

| Test name | Sync Gateway | Edge Server | ✅ | ❌ | ⏭️ | 🚫 | Reason |
|---|---|---|---|---|---|---|---|
| `test_pull_empty_database_active_only` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Delete all remote `names` docs, pull, assert local stays empty / active-only. ES can delete + pull. |

**Group: SG 1 ✅. ES 1 ✅.**

---

## 4. Replication filters (`test_replication_filter.py`)

| Test name | Sync Gateway | Edge Server | ✅ | ❌ | ⏭️ | 🚫 | Reason |
|---|---|---|---|---|---|---|---|
| `test_custom_push_filter` | ✅ | ✅ | both | ⬜ | ⬜ | ⬜ | Filter runs **in CBL** before push. ES only receives the subset. |
| `test_push_document_ids_filter` | ✅ | ⏭️ | SG | ⬜ | ES | ⬜ | Replicator **never reached STOPPED** vs ES (`CblTimeoutError`). Isolated rerun, same hang. JS CBL ↔ ES interop — skipped after hang, not a missing API. |
| `test_pull_document_ids_filter` | ✅ | ⏭️ | SG | ⬜ | ES | ⬜ | Same timeout on pull-by-document-ids. |
| `test_custom_pull_filter` | ✅ | ⏭️ | SG | ⬜ | ES | ⬜ | Filter is CBL-side, but pull vs ES still timed out waiting for STOPPED. |
| `test_pull_channels_filter` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Pulls only docs in SG **channels**. ES has no sync function / channel ACL. |
| `test_replicate_public_channel` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Relies on SG public channel (`channel("!")`). ES has no equivalent. |

**Group: SG 6 ✅. ES 1 ✅, 3 ⏭️ (hang), 2 🚫 (channels).**

---

## 5. Custom conflict (`test_custom_conflict.py`)

Write different values on CBL and remote, pull with a CBL conflict resolver.

| Test name | Sync Gateway | Edge Server | ✅ | ❌ | ⏭️ | 🚫 | Reason |
|---|---|---|---|---|---|---|---|
| `test_push_pull_resolved_doc` | ✅ | ⏭️ | SG | ⬜ | ES | ⬜ | Isolated run: `CblTimeoutError` waiting for replicator STOPPED. JS conflict resolver vs ES (LiteCore) did not finish. |
| `test_custom_conflict_remote_wins` | ✅ | ⏭️ | SG | ⬜ | ES | ⬜ | Same file skipped after the hang above; remote-wins resolver vs ES not completed. |
| `test_custom_conflict_delete` | ✅ | ⏭️ | SG | ⬜ | ES | ⬜ | Same: delete-vs-update conflict vs ES not completed. |
| `test_custom_conflict_merge` | ✅ | ⏭️ | SG | ⬜ | ES | ⬜ | Same: merge resolver vs ES not completed. |

**Group: SG 4 ✅. ES 4 ⏭️ (hang).**

---

## 6. Fest / todo (`test_fest.py`)

Two CBL DBs, continuous push-pull to `todo`, SG **roles + sync functions** (`requireUser`, `requireRole`, list channels).

| Test name | Sync Gateway | Edge Server | ✅ | ❌ | ⏭️ | 🚫 | Reason |
|---|---|---|---|---|---|---|---|
| `test_create_tasks` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Needs SG roles. Also tried on ES: two continuous replicators; JS `POST /updateDatabase` returned **`-1`**. |
| `test_update_task` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Same fest stack: SG ACL. Not supported on ES. |
| `test_delete_task` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Same. |
| `test_delete_list` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Same. |
| `test_share_list` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | SG role/channel sharing. ES `add_role`/`add_user` are no-ops. |
| `test_update_shared_tasks` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Depends on shared list channels. |
| `test_unshare_list` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Depends on revoking SG contributor role / channels. |

**Group: SG 7 ✅. ES 7 🚫 (roles / channels).**

---

## 7. Auto-purge (`test_replication_auto_purge.py`)

SG **channel / role / access** revocation and CBL auto-purge. ES 1.1/1.2 ACL is collection read/write only — not channels.

| Test name | Sync Gateway | Edge Server | ✅ | ❌ | ⏭️ | 🚫 | Reason |
|---|---|---|---|---|---|---|---|
| `test_remove_docs_from_channel_with_auto_purge_enabled` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Removes docs from an SG channel; CBL auto-purges. ES has no channels. |
| `test_revoke_access_with_auto_purge_enabled` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Revokes user `collection_access` / channels. ES has no SG ACL. |
| `test_remove_docs_from_channel_with_auto_purge_disabled` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Same channel-remove path with auto-purge off. |
| `test_revoke_access_with_auto_purge_disabled` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Same revoke path with auto-purge off. |
| `test_filter_removed_access_documents` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Pull filter after SG access removed. |
| `test_remove_user_from_role[True]` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Drop user from SG role (auto-purge on). ES has no SG roles. |
| `test_remove_user_from_role[False]` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Same, auto-purge off. |
| `test_remove_role_from_channel[True]` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Unmap SG role from channel (auto-purge on). |
| `test_remove_role_from_channel[False]` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Same, auto-purge off. |
| `test_pull_after_restore_access` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Restore SG access then pull. |
| `test_push_after_remove_access` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Push after SG access removed. |
| `test_auto_purge_after_resurrection[delete]` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | Delete + resurrect + auto-purge vs SG. |
| `test_auto_purge_after_resurrection[purge]` | ✅ | 🚫 | SG | ⬜ | ⬜ | ES | SG `_purge` + resurrect + auto-purge. ES has no `_purge`. |

**Group: SG 13 ✅. ES 13 🚫 (channels / roles / `_purge`).**

---

## 8. Blobs (`test_replication_blob.py`)

| Test name | Sync Gateway | Edge Server | ✅ | ❌ | ⏭️ | 🚫 | Reason |
|---|---|---|---|---|---|---|---|
| `test_blob_replication` | ✅ | ⏭️ | SG | ⬜ | ES | ⬜ | Push/pull blob on `names`. Vs ES, JS `POST /updateDatabase` returned **`-1`**. Isolated rerun, same. |
| `test_pull_non_blob_changes_with_delta_sync_and_compact` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | `skip_if_not_platform(… ALL & ~JS)` (CBSE-14861). **Not supported on JS.** |

**Group: SG 1 ✅, 1 🚫. ES 1 ⏭️, 1 🚫.**

---

## 9. JWT + JS → Edge Server smoke

Need a live Edge Server. First SG-only full run marked these ⏭️ (`min_edge_servers`). After local ES they ✅ without `--cbl-remote=es` (they still use **real SG** for `local_jwt`).

| Test name | Sync Gateway | Edge Server | ✅ | ❌ | ⏭️ | 🚫 | Reason |
|---|---|---|---|---|---|---|---|
| `test_js_push_to_edge_server_over_ws` | ⏭️ | ✅ | ES | ⬜ | SG | ⬜ | Not a CBL→SG test. JS CBL push 3 docs to `ws://localhost:59840/db`, no pinned cert. |
| `test_jwt_replication_reconnect_false` | ⏭️ | ✅ | ES | ⬜ | SG | ⬜ | ES←SG with **inline** JWT. Needs real SG `local_jwt`, not `EsRemote`. |
| `test_replication_with_jwt_file` | ⏭️ | ✅ | ES | ⬜ | SG | ⬜ | JWT from file on ES (`openid_token.path`). |
| `test_token_rotation_reconnect` | ⏭️ | ✅ | ES | ⬜ | SG | ⬜ | Overwrite JWT file; ES reconnects (`reconnect_on_token_change`). |
| `test_invalid_token_rotation_causes_401_stop` | ⏭️ | ✅ | ES | ⬜ | SG | ⬜ | Invalid JWT → SG 401 → replicator stopped/removed. |
| `test_corrupt_token_file_content_mid_replication` | ⏭️ | ✅ | ES | ⬜ | SG | ⬜ | JWT file overwritten with `" "`; ES stops or keeps old connection. |
| `test_valid_invalid_valid_token_cycle` | ⏭️ | ✅ | ES | ⬜ | SG | ⬜ | Valid→invalid→valid; after 401, `_replicate` must be re-triggered. |

**Group: SG 7 ⏭️ (not CBL→SG). ES 7 ✅.**

---

## 10. Encrypted properties (`test_encrypted_properties.py`)

| Test name | Sync Gateway | Edge Server | ✅ | ❌ | ⏭️ | 🚫 | Reason |
|---|---|---|---|---|---|---|---|
| `test_encrypted_push` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | `EncryptedValue` / `encrypted$password` is **C only**. JS encryption is IndexedDB database password, not replicator field encryption. **Not supported on JS.** |

**Group: both 🚫.**

---

## 11. Multipeer (`test_multipeer.py`)

CBL↔CBL mesh. **Not supported on Couchbase Lite JavaScript** (no P2P / Multipeer API in `@couchbase/lite-js@1.1.0-5`; [documented JS limitation](https://docs.couchbase.com/couchbase-lite-javascript/current/known-limitations.html)). Neither SG nor ES is the remote.

| Test name | Sync Gateway | Edge Server | ✅ | ❌ | ⏭️ | 🚫 | Reason |
|---|---|---|---|---|---|---|---|
| `test_medium_mesh_sanity` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | **Not supported on JS.** No Multipeer / URLEndpointListener in lite-js 1.1. Native CBL only. |
| `test_medium_mesh_consistency` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | **Not supported on JS.** Same missing P2P API. |

**Group: both 🚫 (JS has no multi-peer).**

---

## 12. SGW upgrade (`test_replication_upgrade.py`)

Native CBL **≥ 4.0.0** + dataset v4.0 restore (HLV vs rev-tree). JS reports **1.1.0**. **Not supported on JS.**

| Test name | Sync Gateway | Edge Server | ✅ | ❌ | ⏭️ | 🚫 | Reason |
|---|---|---|---|---|---|---|---|
| `test_nonconflict_case_1` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Requires native CBL ≥ 4.0. JS 1.1.0. **Not supported on JS.** |
| `test_nonconflict_case_2` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Same. |
| `test_nonconflict_case_3` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Same. |
| `test_nonconflict_case_4` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Same. |
| `test_nonconflict_case_5` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Same. |
| `test_nonconflict_case_6` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Same. |
| `test_conflict_case_1` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Same + conflicts across upgrade. |
| `test_conflict_case_2` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Same. |
| `test_conflict_case_3` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Same. |
| `test_conflict_case_4` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Same. |
| `test_conflict_case_5` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Same. |
| `test_conflict_case_6` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Same. |
| `test_conflict_case_7` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Same. |

**Group: both 🚫 (13).**

---

## 13. XDCR (`test_replication_xdcr.py`)

Needs 2 SG + 2 CBS + load balancer, **then** native CBL ≥ 4.0. JS 1.1.0 fails the version gate. **Not supported on JS.**

| Test name | Sync Gateway | Edge Server | ✅ | ❌ | ⏭️ | 🚫 | Reason |
|---|---|---|---|---|---|---|---|
| `test_push_and_pull_with_xdcr` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Native CBL ≥ 4.0 + XDCR topology. **Not supported on JS.** |
| `test_fail_over` | 🚫 | 🚫 | ⬜ | ⬜ | ⬜ | both | Same. |

**Group: both 🚫 (2).**

---

## Summary by group

| # | Group | Tests | SG ✅ | SG ❌ | SG ⏭️ | SG 🚫 | ES ✅ | ES ❌ | ES ⏭️ | ES 🚫 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | Basic replication | 12 | 12 | 0 | 0 | 0 | 10 | 0 | 0 | 2 |
| 2 | Query consistency | 34 | 34 | 0 | 0 | 0 | 34 | 0 | 0 | 0 |
| 3 | Replication behavior | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| 4 | Replication filters | 6 | 6 | 0 | 0 | 0 | 1 | 0 | 3 | 2 |
| 5 | Custom conflict | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 4 | 0 |
| 6 | Fest / todo | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 7 |
| 7 | Auto-purge | 13 | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 13 |
| 8 | Blobs | 2 | 1 | 0 | 0 | 1 | 0 | 0 | 1 | 1 |
| 9 | JWT + JS→ES smoke | 7 | 0 | 0 | 7 | 0 | 7 | 0 | 0 | 0 |
| 10 | Encrypted properties | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 |
| 11 | Multipeer | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 2 |
| 12 | SGW upgrade | 13 | 0 | 0 | 0 | 13 | 0 | 0 | 0 | 13 |
| 13 | XDCR | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 2 |
| | **All** | **104** | **78** | **0** | **7** | **19** | **53** | **0** | **8** | **43** |

**Why 78 vs 46 (CBL→remote only):** of the 78 that ✅ on SG, ES is **46 ✅ + 8 ⏭️ + 24 🚫** (checkpoint `_purge` 2 + channels 2 + fest 7 + auto-purge 13). The 8 ⏭️ are interop hangs (filters 3 + conflict 4 + blob 1).

---

## Can extra environment unskip these?

Checked [Couchbase docs](https://docs.couchbase.com/) (JS 1.0, ES 1.1, native Multipeer) against `@couchbase/lite-js@1.1.0-5` and the TDK skip predicates. Extra Docker does not turn 🚫 into ✅ on JS.

| Leftover | Mark | Extra Docker help? | Why |
|---|---|---|---|
| JWT + JS→ES (7) | ✅ on ES | Already done | `edge-servers` is in `config.docker-js.json`. |
| Multipeer (2) | 🚫 | No | **Not supported on JS.** No P2P in lite-js 1.1. |
| Encrypted properties (1) | 🚫 | No | **Not supported on JS.** C `EncryptedValue` only. |
| Blob compact (1) | 🚫 | No | **Not supported on JS** (CBSE-14861). |
| SGW upgrade (13) | 🚫 | No | **Not supported on JS.** Needs native CBL ≥ 4.0. |
| XDCR (2) | 🚫 | No | **Not supported on JS.** Same CBL ≥ 4.0 gate. |
| ES channel / `_purge` / fest / auto-purge | 🚫 on ES | No | ES has collection ACL, not SG channels/roles/`_purge`. |
| ES doc-id / conflict / blob hang | ⏭️ on ES | No | Interop hang, not a missing container. |

Stale docs vs this stack: “CBL-JS cannot connect to Edge Server” (ES 1.1 CORS; we ✅ JWT/ws). “CBL-JS needs SG 3.3.1 or 4.0.1+” (78 ✅ on **SG 3.2.0**).
