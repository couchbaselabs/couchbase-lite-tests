# Changes

1.2.0 (09/23/2026)
* Add test_nonconflict_case_7 : pull a legacy-only doc into an empty database, then pull a post-upgrade SGW mutation of it.
* Add test_nonconflict_case_8 : pull the non-conflict docs (most with legacy-only revisions) into an empty database, update one on SGW, pull again with the checkpoint reset.
* Add test_nonconflict_case_9 : pull a doc the upgraded database already has at the same legacy revision, then pull a post-upgrade SGW mutation of it.
* Add test_conflict_case_8    : resolve a pre-upgrade conflict with remote wins, then pull a post-upgrade SGW mutation of the doc.

1.1.0 (09/22/2026)
* Group the test cases into "Non Conflict Cases" and "Conflict Cases" sections.
* Number the test cases as #<section>.<case> and add a descriptive name after each test name.

1.0.1 (08/26/2026)
* All test cases: remove the "Delete Sync Gateway database" step and the fixed 2s wait from the setup steps; wait for Sync Gateway to bring the restored database online instead (CBG-5723).

1.0.0 (10/22/2025)
* Initial version: 6 non-conflict and 7 conflict upgrade test cases.

# Test Cases

## #1 Non Conflict Cases

### #1.1 test_nonconflict_case_1 (push_pre_upgrade_cbl_mutation)
#### Description

Bidirectional replication where CBL has a pre-upgrade mutation that hasn’t been 
replicated — a mutation made on CBL before the 4.x upgrade has not yet been pushed.

```
+------------------+-------------------------------+-------------------------------+
|                  |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| Initial State    |  2-def, 1-abc |      none     |     1-abc     |      none     |
| Expected Result  |  2-def, 1-abc |      none     |  2-def, 1-abc | Encoded 2-def |
+------------------+---------------+---------------+---------------+---------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
   * endpoint: '/upgrade'
   * collections : '_default._default'
   * type: pushAndPull
   * document_ids: ['nonconflict_1']
   * continuous: False
5. Wait until the replicator is stopped.
6. Check that the doc is replicated correctly.
7. Validate revid and HLV of local and remote doc.

### #1.2 test_nonconflict_case_2 (pull_pre_upgrade_sgw_mutation)
#### Description

Bidirectional replication where SGW has a pre-upgrade mutation that hasn’t been 
replicated — a mutation made on SGW before the 4.x upgrade has not yet been pulled.

```
+------------------+-------------------------------+-------------------------------+
|                  |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| Initial State    |     1-abc     |      none     |  2-def,1-abc  |      none     |
| Expected Result  |  2-def,1-abc  | Encoded 2-def |     2-def     |      none     |
+------------------+---------------+---------------+---------------+---------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pushAndPull
	* document_ids: ['nonconflict_2']
	* continuous: False
5. Wait until the replicator is stopped.
6. Check that the doc is replicated correctly.
7. Validate revid and HLV of local and remote doc.

### #1.3 test_nonconflict_case_3 (push_pull_pre_upgrade_cbl_mutation_already_on_sgw)
#### Description

Bidirectional replication where CBL has a pre-upgrade mutation that SGW
already knows — a mutation made on CBL before the 4.x upgrade has not
been pushed, but was already pushed earlier by another peer.

```
+------------------+-------------------------------+-------------------------------+
|                  |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| Initial State    |     2-abc     |      none     |     2-abc     |      none     |
| Expected Result  |     2-abc     |      none     |     2-abc     |      none     |
+------------------+---------------+---------------+---------------+---------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pushAndPull
	* document_ids: ['nonconflict_3']
	* continuous: False
5. Wait until the replicator is stopped.
6. Check that the doc is replicated correctly.
7. Validate revid and HLV of local and remote doc.

### #1.4 test_nonconflict_case_4 (push_pull_post_upgrade_sgw_mutation_with_cbl_ancestor)
#### Description

Bidirectional replication where CBL has a pre-upgrade mutation that is already in
SGW’s history and SGW includes post-upgrade mutations — a mutation made on CBL
before the 4.x upgrade has not been pushed, but was previously pushed by
another peer and already exists in SGW’s revision tree history.

```
+------------------+-------------------------------+-------------------------------+
|                  |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| Initial State    |     2-def     |      none     |  3-ghi 2-def  |   [100@SGW1]  |
| Expected Result  |      none     |  [100@SGW1]   |  3-ghi 2-def  |   [100@SGW1]  |
+------------------+---------------+---------------+---------------+---------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pushAndPull
	* document_ids: ['nonconflict_4']
	* continuous: False
5. Wait until the replicator is stopped.
6. Check that the doc is replicated correctly.
7. Validate revid and HLV of local and remote doc.

### #1.5 test_nonconflict_case_5 (pull_post_upgrade_sgw_mutation_with_cbl_ancestor)
#### Description

CBL pull of a post-upgrade mutation that shares a common ancestor with the
CBL version — SGW has a new mutation with the CBL revTreeID as its ancestor,
and CBL should recognize it as non-conflicting and pull the new revision.

```
+------------------+-------------------------------+-------------------------------+
|                  |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| Initial State    |     2-def     |      none     |  3-ghi 2-def  |   [100@SGW1]  |
| Expected Result  |      none     |   [100@SGW1]  |  3-ghi 2-def  |   [100@SGW1]  |
+------------------+---------------+---------------+---------------+---------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['nonconflict_5']
	* continuous: False
5. Wait until the replicator is stopped.
6. Check that the doc is replicated correctly.
7. Validate revid and HLV of local and remote doc.

### #1.6 test_nonconflict_case_6 (push_post_upgrade_cbl_mutation_with_sgw_ancestor)
#### Description

CBL push of a post-upgrade mutation that shares a common ancestor with the
SGW version — CBL has a post-upgrade mutation with the same revTreeID ancestor
as the SGW version, and SGW should recognize it as non-conflicting and accept
the pushed revision.

```
+------------------+------------------------------------------------+-------------------------------+
|                  |                       CBL                      |              SGW              |
|                  +------------------------+------------------------+---------------+---------------+
|                  |        Rev Tree        |         HLV            |   Rev Tree    |      HLV      |
+------------------+------------------------+------------------------+---------------+---------------+
| Initial State    | none (parent = 2-abc)  | [100@CBL1]             |     2-abc     |      none      |
| Expected Result  |         none           | [100@CBL1]             |     3-def     |   [100@CBL1]   |
+------------------+------------------------+------------------------+---------------+---------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['nonconflict_6']
	* continuous: False
5. Wait until the replicator is stopped.
6. Check that the doc is replicated correctly.
7. Validate revid and HLV of local and remote doc.

### #1.7 test_nonconflict_case_7 (pull_legacy_doc_then_pull_update)

#### Description

Pull of a document that CBL does not have and that SGW still holds with a legacy
(pre-upgrade) revision only, followed by a post-upgrade SGW mutation of the same
document. The first pull stores the document with its legacy revID in the 4.x record
format; the second pull must accept the new revision (CBL-8954).

```
+------------------+-------------------------------+-------------------------------+
|                  |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| Initial State    |     none      |      none     |  2-def,1-abc  |      none     |
| After first pull |     2-def     |      none     |  2-def,1-abc  |      none     |
| After SGW update |     2-def     |      none     |  3-ghi 2-def  |   [100@SGW1]  |
| Expected Result  |     none      |   [100@SGW1]  |  3-ghi 2-def  |   [100@SGW1]  |
+------------------+---------------+---------------+---------------+---------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `empty` dataset.
4. Start a replicator:
   * endpoint: '/upgrade'
   * collections : '_default._default'
   * type: pull
   * document_ids: ['nonconflict_2']
   * continuous: False
5. Wait until the replicator is stopped.
6. Check that the doc is replicated correctly.
7. Validate revid and HLV of local and remote doc.
8. Update `nonconflict_2` on SGW.
9. Start the replicator in step 4 again.
10. Wait until the replicator is stopped.
11. Check that the doc is replicated correctly.
12. Validate revid and HLV of local and remote doc.

### #1.8 test_nonconflict_case_8 (pull_legacy_docs_then_pull_update_with_reset)

#### Description

Pull of several documents that CBL does not have, most of them held by SGW with legacy
revisions only, followed by a post-upgrade SGW mutation of one of them and a second pull
with the checkpoint reset. SGW then sends all documents in one `changes` batch. The batch
must be processed, only the updated document must be pulled, and the other documents must
be unchanged (CBL-8954).

```
+------------------+-------------------------------+-------------------------------+
| nonconflict_2    |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| Initial State    |     none      |      none     |  2-def,1-abc  |      none     |
| After first pull |     2-def     |      none     |  2-def,1-abc  |      none     |
| After SGW update |     2-def     |      none     |  3-ghi 2-def  |   [100@SGW1]  |
| Expected Result  |     none      |   [100@SGW1]  |  3-ghi 2-def  |   [100@SGW1]  |
+------------------+---------------+---------------+---------------+---------------+
```

All other documents keep the revid and HLV they had after the first pull.

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `empty` dataset.
4. Start a replicator:
   * endpoint: '/upgrade'
   * collections : '_default._default'
   * type: pull
   * document_ids: ['nonconflict_1', 'nonconflict_2', 'nonconflict_3', 'nonconflict_4', 'nonconflict_5', 'nonconflict_6']
   * continuous: False
5. Wait until the replicator is stopped.
6. Check that all docs are replicated correctly.
7. Update `nonconflict_2` on SGW.
8. Start the replicator in step 4 again with `reset: True`.
9. Wait until the replicator is stopped.
10. Check that all docs are replicated correctly.
11. Validate revid and HLV of local and remote docs.
12. Check that only `nonconflict_2` was pulled.

### #1.9 test_nonconflict_case_9 (pull_upgraded_db_then_pull_update)

#### Description

Pull of a document that CBL already has at the same legacy revision as SGW, followed
by a post-upgrade SGW mutation of that document. The first pull transfers nothing but
records SGW's revision on the local document, which rewrites it into the 4.x record
format while keeping its legacy revID. The second pull must accept the new revision
(CBL-8954).

Note: the rewrite in the first pull happens only because the `upgrade` dataset has no
remote mark for the test's SGW URL.

```
+------------------+-------------------------------+-------------------------------+
|                  |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| Initial State    |     2-abc     |      none     |     2-abc     |      none     |
| After first pull |     2-abc     |      none     |     2-abc     |      none     |
| After SGW update |     2-abc     |      none     |  3-ghi 2-abc  |   [100@SGW1]  |
| Expected Result  |     none      |   [100@SGW1]  |  3-ghi 2-abc  |   [100@SGW1]  |
+------------------+---------------+---------------+---------------+---------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
   * endpoint: '/upgrade'
   * collections : '_default._default'
   * type: pull
   * document_ids: ['nonconflict_3']
   * continuous: False
5. Wait until the replicator is stopped.
6. Check that the doc is replicated correctly.
7. Validate revid and HLV of local and remote doc.
8. Check that no doc was pulled.
9. Update `nonconflict_3` on SGW.
10. Start the replicator in step 4 again.
11. Wait until the replicator is stopped.
12. Check that the doc is replicated correctly.
13. Validate revid and HLV of local and remote doc.
14. Check that `nonconflict_3` was pulled.

## #2 Conflict Cases

### #2.1 test_conflict_case_1 (push_pre_upgrade_conflict)
#### Description

Push replication with a conflict between pre-upgrade CBL and SGW mutations —
both sides have conflicting legacy revisions created before the 4.x upgrade.

```
+------------------+-------------------------------+-------------------------------+
|                  |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| Initial State    |     3-abc     |      none     |     3-def     |      none     |
| Expected Result  |     3-abc     |      none     |     3-def     |      none     |
+------------------+---------------+---------------+---------------+---------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_1']
	* continuous: False
 6. Wait until the replicator is stopped.  
 7. Validate revid and HLV of local and remote doc.

### #2.2 test_conflict_case_2 (pull_pre_upgrade_conflict_remote_wins)
#### Description

Bidirectional replication conflict between pre-upgrade CBL and SGW mutations,
resolved by the default conflict resolver where SGW wins — both SGW and CBL
have conflicting legacy revisions created before the 4.x upgrade,
with SGW chosen as the winner under the legacy default conflict resolution.

```
+------------------+-------------------------------+-------------------------------+
|                  |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| Initial State    |     3-abc     |      none     |     3-def     |      none     |
| Expected Result  |     3-def     |      none     |     3-def     |      none     |
+------------------+---------------+---------------+---------------+---------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['conflict_2']
	* continuous: False
   * conflict_resolver: remote-wins
5. Wait until the replicator is stopped.
6. Check that the doc is replicated correctly.
7. Validate revid and HLV of local and remote doc.
8. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_2']
	* continuous: False
9. Wait until the replicator is stopped.
10. Check that the doc is replicated correctly.
11. Validate revid and HLV of local and remote doc.

### #2.3 test_conflict_case_3 (pull_post_upgrade_sgw_conflict_remote_wins)
#### Description

Bidirectional replication conflict between a pre-upgrade CBL mutation and a post-upgrade
SGW mutation, resolved by the default conflict resolver where SGW wins — SGW and CBL
have conflicting revisions, with SGW’s post-upgrade revision selected as the winner
under the default conflict resolution.

```
+------------------+-------------------------------+-------------------------------+
|                  |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| Initial State    |     3-abc     |      none     |     3-def     |  [100@SGW1]   |
| Expected Result  |      none     |  [100@SGW1]   |     3-def     |  [100@SGW1]   |
+------------------+---------------+---------------+---------------+---------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['conflict_3']
	* continuous: False
   * conflict_resolver: remote-wins
5. Wait until the replicator is stopped.
6. Check that the doc is replicated correctly.
7. Validate revid and HLV of local and remote doc.
8. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_3']
	* continuous: False
9. Wait until the replicator is stopped.
10. Check that the doc is replicated correctly.
11. Validate revid and HLV of local and remote doc.

### #2.4 test_conflict_case_4 (pull_pre_upgrade_conflict_local_wins)
#### Description

Bidirectional replication conflict between pre-upgrade CBL and SGW mutations,
resolved by the default conflict resolver where CBL wins — SGW and CBL have
conflicting legacy revisions, with CBL chosen as the winner under the legacy
default conflict resolution. CBL will rewrite the local winning revision
as a child of the remote revision and push it to SGW.

```
+------------------+--------------------------------------+--------------------------------------+
|                  |              CBL                     |                 SGW                  |
|                  +---------------+----------------------+---------------+----------------------+
|                  |   Rev Tree    |         HLV          |   Rev Tree    |         HLV          |
+------------------+---------------+----------------------+---------------+----------------------+
| Initial State    |     3-def     |      none            |     3-abc     |      none            |
| Expected Result  |      none     | [100@CBL1, 3abc@RTE] |     4-def     | [100@CBL1, 3abc@RTE] |
+------------------+---------------+----------------------+---------------+----------------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['conflict_4']
	* continuous: False
   * conflict_resolver: local-wins
5. Wait until the replicator is stopped.
6. Validate revid and HLV of local and remote doc.
7. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_4']
	* continuous: False
8. Wait until the replicator is stopped.
9. Check that the doc is replicated correctly.
10. Validate revid and HLV of local and remote doc.

### #2.5 test_conflict_case_5 (pull_post_upgrade_sgw_conflict_local_wins)
#### Description

Bidirectional replication conflict between a pre-upgrade CBL mutation and
a post-upgrade SGW mutation, resolved by the default conflict resolver
where CBL wins — SGW and CBL have conflicting revisions, with CBL selected
as the winner under the legacy default conflict resolution. CBL will rewrite 
the local winning revision as a child of the remote revision and push it to SGW.

```
+------------------+------------------------------------+------------------------------------+
|                  |                   CBL              |            SGW                     |
|                  +-------------+----------------------+-------------+----------------------+
|                  |  Rev Tree   |         HLV          |  Rev Tree   |          HLV         |
+------------------+-------------+----------------------+-------------+----------------------+
| Initial State    |    3-def    |         none         |    3-abc    | [100@SGW1]           |
| Expected Result  |             | [3def@RTE, 100@SGW1] |    4-def    | [3def@RTE, 100@SGW1] |
+------------------+-------------+----------------------+-------------+----------------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['conflict_5']
	* continuous: False
   * conflict_resolver: local-wins
5. Wait until the replicator is stopped.
6. Validate revid and HLV of local and remote doc.
7. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_5']
	* continuous: False
8. Wait until the replicator is stopped.
9. Check that the doc is replicated correctly.
10. Validate revid and HLV of local and remote doc.

### #2.6 test_conflict_case_6 (pull_post_upgrade_cbl_conflict_local_wins)
#### Description

Bidirectional replication conflict between a post-upgrade CBL mutation and
a pre-upgrade SGW mutation, resolved with local wins — SGW and CBL have
conflicting revisions, with CBL selected as the winner under the legacy
default conflict resolution. CBL will rewrite the local winning revision
as a child of the remote revision and push it to SGW.

```
+------------------+-------------------------------------+-------------------------------------+
|                  |                    CBL              |                   SGW               |
|                  +--------------+----------------------+--------------+----------------------+
|                  |  Rev Tree    |          HLV         |   Rev Tree   |         HLV          |
+------------------+--------------+----------------------+--------------+----------------------+
| Initial State    |    none      | [100@CBL1]           |   3-abc      |          none        |
| Expected Result  |              | [100@CBL1, 3abc@RTE] |   4-abc      | [100@CBL1, 3abc@RTE] |
+------------------+--------------+----------------------+--------------+----------------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['conflict_6']
	* continuous: False
   * conflict_resolver: local-wins
5. Wait until the replicator is stopped.
6. Validate revid and HLV of local and remote doc.
7. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_6']
	* continuous: False
8. Wait until the replicator is stopped.
9. Check that the doc is replicated correctly.
10. Validate revid and HLV of local and remote doc.

### #2.7 test_conflict_case_7 (pull_post_upgrade_cbl_conflict_remote_wins)
#### Description

Bidirectional replication conflict between a post-upgrade CBL mutation and
a pre-upgrade SGW mutation, resolved with remote wins — SGW and CBL have
conflicting revisions, with the remote revision selected as the winner
under the legacy default conflict resolution. CBL will rewrite the local
winning revision as a child of the remote revision and push it to SGW.

```
+------------------+---------------------------+---------------------------+
|                  |            CBL            |            SGW            |
|                  +-------------+-------------+-------------+-------------+
|                  |  Rev Tree   |     HLV     |  Rev Tree   |     HLV     |
+------------------+-------------+-------------+-------------+-------------+
| Initial State    |    none     |  [100@CBL1] |    3-abc    |     none    |
| Expected Result  |             |   3abc@RTE  |    3-abc    |     none    |
+------------------+-------------+-------------+-------------+-------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['conflict_6']
	* continuous: False
   * conflict_resolver: local-wins
5. Wait until the replicator is stopped.
6. Validate revid and HLV of local and remote doc.
7. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_6']
	* continuous: False
8. Wait until the replicator is stopped.
9. Validate revid and HLV of local and remote doc.

### #2.8 test_conflict_case_8 (pull_conflict_remote_wins_then_pull_update)

#### Description

Pull replication conflict between pre-upgrade CBL and SGW mutations resolved with
remote wins, followed by a post-upgrade SGW mutation of the same document. After the
resolution CBL holds SGW's legacy revision, pulled with a legacy-only history, in the
4.x record format. The second pull must accept the new revision (CBL-8954).

```
+------------------+-------------------------------+-------------------------------+
|                  |             CBL               |              SGW              |
|                  +---------------+---------------+---------------+---------------+
|                  |   Rev Tree    |      HLV      |   Rev Tree    |      HLV      |
+------------------+---------------+---------------+---------------+---------------+
| Initial State    |     3-abc     |      none     |     3-def     |      none     |
| After first pull |     3-def     |      none     |     3-def     |      none     |
| After SGW update |     3-def     |      none     |  4-ghi 3-def  |   [100@SGW1]  |
| Expected Result  |     none      |   [100@SGW1]  |  4-ghi 3-def  |   [100@SGW1]  |
+------------------+---------------+---------------+---------------+---------------+
```

#### Steps

1. Restore Couchbase Server Bucket using `upgrade` dataset.
2. Wait for SG to bring the restored database online.
3. Reset local database, and load `upgrade` dataset.
4. Start a replicator:
   * endpoint: '/upgrade'
   * collections : '_default._default'
   * type: pull
   * document_ids: ['conflict_2']
   * continuous: False
   * conflict_resolver: remote-wins
5. Wait until the replicator is stopped.
6. Check that the doc is replicated correctly.
7. Validate revid and HLV of local and remote doc.
8. Update `conflict_2` on SGW.
9. Start the replicator in step 4 again.
10. Wait until the replicator is stopped.
11. Check that the doc is replicated correctly.
12. Validate revid and HLV of local and remote doc.
13. Check that `conflict_2` was pulled.
