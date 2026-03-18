# SGW Rolling Upgrade Tests

## test_rolling_upgrade_sgw_cluster

Rolling upgrade test for Sync Gateway clusters with one-at-a-time node upgrades.

### Description

This test validates a true rolling upgrade scenario where Sync Gateway nodes in a 3-node cluster are upgraded **one node at a time** while the remaining nodes stay on the old version. It verifies:

1. **Cluster consistency**: Revisions remain synchronized across mixed-version nodes
2. **Cross-version read/write**: Documents created by old-version nodes are readable by new-version nodes and vice versa
3. **Replication integrity**: CBL replicators work seamlessly during mixed-version states
4. **Data persistence**: All data survives across the entire rolling upgrade sequence

### Topology Requirements
- **Minimum 3 Sync Gateway nodes** (for rolling one-at-a-time)
- **Minimum 1 Couchbase Server node**
- **Minimum 1 CBL/Test Server**
- **Load Balancer**: Optional (tested if present)

### Test Phases

The test adapts its behavior based on `SGW_UPGRADE_PHASE` environment variable:

#### Phase: `initial`
Setup phase with all 3 nodes on the same version.

**Steps**:
1. Create bucket `rolling_upg_bucket` on CBS
2. Reset CBL database `rolling_upg_cbl`
3. Configure SGW database on all 3 nodes with:
   - `revs_limit: 1000`
   - `enable_shared_bucket_access: true`
   - `delta_sync: enabled`
   - Sync function: `channel("upgrade")`
4. Create user `user1` on all 3 nodes with full `_default._default` access
5. Ingest 30 documents (10 per node) via SGW admin API:
   - `type: rolling_upgrade_doc`
   - `created_by_node: N` (0, 1, or 2)
   - `version: <current_version>`
   - `content: "Initial doc created via node N"`
6. Start continuous push-pull replicator from node 0
7. Wait for replicator to IDLE with no errors
8. **Verify all 30 docs replicated to CBL**
9. **Verify revision consistency across all 3 nodes** (all revision IDs match)

**Expected outcome**: All documents synced, cluster consistent, ready for rolling upgrade.

---

#### Phase: `rolling_node_N` (Mixed-Version State)
Upgrade phase after node N has been upgraded to the new version, while other nodes remain on the old version.

**Environment variables set**:
- `SGW_UPGRADED_NODE_INDEX`: 0, 1, or 2 (which node was just upgraded)
- `SGW_VERSION_UNDER_TEST`: New version (node N is running this)
- `SGW_PREVIOUS_VERSION`: Old version (other nodes running this)

**Steps**:

1. **Wait for upgraded node online**: Call `wait_for_db_up(sg_db)` on the upgraded node N
2. **Cross-version read verification**:
   - Get all documents from upgraded node N (new version) → verify count > 0
   - Get all documents from each old-version node → verify same count
   - Assert: doc counts match across all nodes
3. **Cross-version write verification**:
   - Write 5 new documents via upgraded node N
   - Verify all 5 are readable from old-version nodes (after ~1 sec sync)
   - Write 5 new documents via an old-version node
   - Verify all 5 are readable from upgraded node N (after ~1 sec sync)
4. **Replicator connectivity**:
   - Start individual continuous push-pull replicators from CBL to **each** node
   - All replicators must reach IDLE with no errors
   - **If load balancer in topology**: Start additional replicator through LB, verify IDLE with no errors
5. **Revision consistency in mixed-version**: 
   - Get all documents from all 3 nodes
   - For each document, assert revision ID is identical across all nodes
   - Mixed-version cluster must maintain revision synchronization
6. **CBS spot-check**:
   - Pick first 5 documents from any node
   - For each, verify it exists on CBS
   - Verify `type`, `version`, and `content` fields are present and correct

**Expected outcome**: 
- ✅ Mixed-version cluster remains consistent
- ✅ Old-version and new-version nodes can read/write to each other's documents
- ✅ Replicators (direct and through LB) function correctly
- ✅ No revision conflicts or sync delays

---

#### Phase: `complete`
Final phase after all 3 nodes have been upgraded to the new version.

**Steps**:

1. **Verify all documents present** from all upgrade phases:
   - 30 initial docs (from `initial` phase)
   - 5 docs per rolling phase per node (3 nodes × 3 rolling phases = 45 docs from rolling)
   - Total: ~75 documents expected
2. **Full 3-way verification: SGW (all nodes) == CBS == CBL**:
   - Get all documents from all 3 SGW nodes → verify all have same count
   - For each document:
     - Assert exists on CBS
     - Assert exists on CBL
     - Verify `type`, `version`, `content` fields match
3. **Final replicator round-trip**:
   - Start push-pull replicator from CBL to SGW node 0
   - Wait until STOPPED with no errors
   - Verify final document count unchanged
4. **Data integrity**:
   - No documents lost across the entire rolling upgrade sequence
   - All revision histories intact (revisions progressed correctly)

**Expected outcome**: 
- ✅ All ~75 documents intact across SGW cluster, CBS, and CBL
- ✅ No data loss during rolling upgrade
- ✅ Cluster fully synchronized on new version

---

### Command-Line Invocation

The rolling upgrade is orchestrated by `jenkins/pipelines/QE/upg-sgw/test_rolling.sh`:

```bash
# Upgrade through multiple versions, one node at a time
./test_rolling.sh 4.0.0 3.2.7 3.3.3 4.0.0

# First invocation (3.2.7):
#   1. Full setup: all 3 nodes on 3.2.7
#   2. Run INITIAL phase test
#   3. Upgrade node 0 to 3.2.7 (trivial, same version)
#   4. Run ROLLING_NODE_0 phase test
#   5. Upgrade node 1 to 3.2.7
#   6. Run ROLLING_NODE_1 phase test
#   7. Upgrade node 2 to 3.2.7
#   8. Run ROLLING_NODE_2 phase test
#   9. Run COMPLETE phase test

# Second invocation (3.3.3):
#   1. Upgrade node 0 to 3.3.3 (mixed: 3.3.3 + 3.2.7 + 3.2.7)
#   2. Run ROLLING_NODE_0 phase test
#   3. Upgrade node 1 to 3.3.3 (mixed: 3.3.3 + 3.3.3 + 3.2.7)
#   4. Run ROLLING_NODE_1 phase test
#   5. Upgrade node 2 to 3.3.3 (mixed: 3.3.3 + 3.3.3 + 3.3.3)
#   6. Run ROLLING_NODE_2 phase test
#   7. Run COMPLETE phase test

# ... repeat for each remaining version
```

---

### Key Test Characteristics

**Rolling Upgrade Pattern**:
- ✅ Nodes upgraded **one at a time** (not in parallel)
- ✅ Cluster stays **partially operational** during upgrade (2 nodes old, 1 new)
- ✅ Happens **3 times per version** (once per node)
- ✅ Repeats for **each new version** specified

**Verification**:
- ✅ Revision IDs synchronized across mixed-version cluster
- ✅ Cross-version read/write capability tested
- ✅ Replicator failover scenarios (individual nodes + load balancer)
- ✅ Data integrity across full rolling upgrade sequence

**Data Persistence**:
- Initial 30 docs persist through all rolling phases
- New docs created during rolling persist until final phase
- Total doc count tracked and verified
- No data loss assertions at every phase

---

### Expected Outcomes

| Phase | Verification | Pass Criteria |
|-------|--------------|---------------|
| `initial` | Cluster consistent, 30 docs replicated | All revisions match, CBL has all docs |
| `rolling_node_N` | Mixed-version consistency, cross-version R/W | Revisions match, cross-writes visible, LB works |
| `complete` | All docs intact, 3-way sync | All docs on SGW/CBS/CBL, no loss |

---

### Environment Variables

| Variable | Phase | Example | Purpose |
|----------|-------|---------|---------|
| `SGW_UPGRADE_PHASE` | All | `rolling_node_1` | Determines test behavior |
| `SGW_UPGRADED_NODE_INDEX` | rolling_node_* | `0`, `1`, `2` | Which node to verify |
| `SGW_VERSION_UNDER_TEST` | All | `3.3.3` | New version being rolled out |
| `SGW_PREVIOUS_VERSION` | rolling_node_* | `3.2.7` | Old version for comparison |

---

### Markers

- `@pytest.mark.upg_sgw` — SGW upgrade test
- `@pytest.mark.min_sync_gateways(3)` — Requires 3 SGW nodes
- `@pytest.mark.min_couchbase_servers(1)` — Requires 1 CBS node
- `@pytest.mark.asyncio(loop_scope="session")` — Async test, session-scoped loop
