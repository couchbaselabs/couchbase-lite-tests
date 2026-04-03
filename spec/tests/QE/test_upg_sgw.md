# SGW Upgrade Tests

## test_replication_and_persistence_after_upgrade

Basic upgrade test verifying data persistence across SGW upgrades.

### Description
This test runs after each SGW upgrade iteration. It validates two critical aspects:
1. **Functional verification**: Newly upgraded SGW can create and replicate documents correctly
2. **Data persistence**: All documents from previous upgrade iterations remain intact and consistent

### Steps

1. Get current SGW version from `SGW_VERSION_UNDER_TEST` environment variable
2. Create bucket on CBS (reuse across iterations)
3. Reset CBL database (persistent across upgrade iterations)
4. Configure SGW database with:
   - `revs_limit: 1000`
   - `enable_shared_bucket_access: true`
   - `delta_sync: enabled`
   - Simple sync function: `channel("upgrade")`
5. Create user `user1` with full access to `_default._default` collection
6. Create 10 new documents via SGW with metadata:
   - `type: upgrade_test_doc`
   - `version: <current_sgw_version>`
   - `index: 0-9`
7. Start PULL replicator from SGW to CBL:
   - `endpoint: /upg_db`
   - `collections: _default._default`
   - `type: pull`
   - `continuous: false`
   - `credentials: user1/pass`
8. Wait until replicator stops with `STOPPED` activity level and no errors
9. For each document on SGW:
   - Verify document exists on CBS with correct metadata
   - Verify document exists on CBL with correct metadata
   - Verify `type`, `version`, and `index` fields match

---

## test_upgrade_multi_sgw_with_revision_history

Advanced upgrade test validating multi-node SGW cluster consistency and revision history progression.

### Description
This test validates a complex upgrade scenario with multiple SGW nodes, demonstrating:
1. **Cluster consistency**: Both SGW nodes maintain identical revision state
2. **Revision progression**: Document revisions increment correctly through 3 generations
3. **Multi-directional replication**: SGW → CBL → SGW → CBL (conflict resolution)
4. **Round-robin updates**: Both SGW nodes participate in updates
5. **Delta sync**: Works correctly with multi-revision documents

### Topology Requirements
- **Minimum 2 Sync Gateway nodes** (cluster)
- **Minimum 1 Couchbase Server node**
- **Minimum 1 CBL/Test Server**

### Steps

#### Setup Phase
1. Get 2 SGW nodes, 1 CBS instance, 1 CBL instance
2. Get current SGW version from `SGW_VERSION_UNDER_TEST` environment variable
3. Create bucket `upg_multi_bucket` on CBS
4. Reset CBL database `upg_multi_sgw` (persistent across iterations)
5. Configure SGW database on BOTH nodes with:
   - Sync function: Increments `update_count` on each revision change
   - `revs_limit: 1000`
   - `delta_sync: enabled`
   - `enable_shared_bucket_access: true`
6. Create user `user1` on both SGW nodes with full collection access

#### Generation 1: Create via SGW Node 1
7. Create 20 documents via SGW node 1 with:
   - `generation: 1`
   - `content: "Gen 1 - doc {i}"`
   - `created_via: sgw_node_1`
   - `upgrade_version: <current_sgw_version>`
8. Store revision IDs (`_rev`) from SGW node 1 for all 20 documents
9. Store revision IDs (`_rev`) from SGW node 2 for all 20 documents
10. **Verify cluster consistency**: All 20 revision IDs must match between node 1 and node 2
11. Start PULL replicator to CBL from SGW node 1:
    - `type: pull`
    - `continuous: false`
12. Wait for PULL to complete with no errors

#### Generation 2: Update via CBL
13. Update all 20 documents on CBL with:
    - `generation: 2`
    - `content: "Gen 2 (updated via CBL) - doc {i}"`
    - `last_updated_via: cbl`
    - Use batch updater (`async with db.batch_updater()`)
14. Start PUSH replicator to SGW node 1:
    - `type: push`
    - `continuous: false`
15. Wait for PUSH to complete with no errors

#### Generation 3: Update via Both SGW Nodes (Round-Robin)
16. Create updates for all 20 documents:
    - Even-indexed (0, 2, 4, ...) → Send to SGW node 1
    - Odd-indexed (1, 3, 5, ...) → Send to SGW node 2
    - `generation: 3`
    - `content: "Gen 3 (updated via SGW multi-node) - doc {i}"`
    - `created_via: sgw_multi_node`
17. Store revision IDs (`_rev`) from SGW node 1 for all 20 documents
18. Store revision IDs (`_rev`) from SGW node 2 for all 20 documents
19. **Verify cluster consistency**: All 20 final revision IDs must match between node 1 and node 2

#### Revision Progression Verification
20. For each document:
    - Extract generation number from Gen 1 revision (format: `N-xxx`)
    - Extract generation number from Gen 3 revision
    - **Assert**: Gen 3 revision number > Gen 1 revision number
    - **Example**: Gen1=`1-abc123`, Gen3=`3-xyz789` ✓

#### Final Sync: Pull Gen 3 to CBL
21. Start PULL replicator to CBL from SGW node 2:
    - `type: pull`
    - `continuous: false`
22. Wait for PULL to complete with no errors

#### Final 3-Way Verification
23. For each of the 20 documents:
    - **On CBS**: Document exists, `generation == 3`, all fields present
    - **On SGW**: Document exists with final revision, `generation == 3`
    - **On CBL**: Document exists, `generation == 3`, content matches SGW
    - **Assert**: Content is identical across CBS, SGW cluster, and CBL
24. **Assert**: All 20 documents successfully synchronized across 3 generations

### Expected Outcome

✅ **Cluster consistency maintained**: Both SGW nodes always have identical revisions  
✅ **Revision progression verified**: Gen 1 → Gen 2 → Gen 3 (revision numbers increment)  
✅ **Conflict resolution works**: CBL update → SGW (merged correctly)  
✅ **Round-robin updates**: Both nodes participate, cluster stays consistent  
✅ **Delta sync functional**: Works with multi-revision documents  
✅ **Data persistence**: All data survives across 3 generations and both nodes  
✅ **Multi-directional replication**: SGW → CBL → SGW → CBL all work correctly

