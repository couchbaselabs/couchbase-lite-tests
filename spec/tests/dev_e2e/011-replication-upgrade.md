# Test Cases

## #1 test_nonconflict_case_1

### Description

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

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Start a replicator:
   * endpoint: '/upgrade'
   * collections : '_default._default'
   * type: pushAndPull
   * document_ids: ['nonconflict_1']
   * continuous: False
6. Wait until the replicator is stopped.
7. Check that the doc is replicated correctly.
8. Validate revid and HLV of local and remote doc.   

## #2 test_nonconflict_case_2

### Description

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

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pushAndPull
	* document_ids: ['nonconflict_2']
	* continuous: False
6. Wait until the replicator is stopped.
7. Check that the doc is replicated correctly.
8. Validate revid and HLV of local and remote doc.

## #3 test_nonconflict_case_3

### Description

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

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pushAndPull
	* document_ids: ['nonconflict_3']
	* continuous: False
6. Wait until the replicator is stopped.
7. Check that the doc is replicated correctly.
8. Validate revid and HLV of local and remote doc.

## #4test_nonconflict_case_4

### Description

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

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pushAndPull
	* document_ids: ['nonconflict_4']
	* continuous: False
6. Wait until the replicator is stopped.
7. Check that the doc is replicated correctly.
8. Validate revid and HLV of local and remote doc.

## #5 test_nonconflict_case_5

### Description

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

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['nonconflict_5']
	* continuous: False
6. Wait until the replicator is stopped.
7. Check that the doc is replicated correctly.
8. Validate revid and HLV of local and remote doc.

## #6 test_nonconflict_case_6

### Description

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

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['nonconflict_6']
	* continuous: False
6. Wait until the replicator is stopped.
7. Check that the doc is replicated correctly.
8. Validate revid and HLV of local and remote doc.

## #7 test_conflict_case_1

### Description

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

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_1']
	* continuous: False
 6. Wait until the replicator is stopped.  
 7. Validate revid and HLV of local and remote doc.

## #8 test_conflict_case_2

### Description

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

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['conflict_2']
	* continuous: False
   * conflict_resolver: remote-wins
6. Wait until the replicator is stopped.  
7. Check that the doc is replicated correctly.
8. Validate revid and HLV of local and remote doc.
9. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_2']
	* continuous: False
10. Wait until the replicator is stopped.  
11. Check that the doc is replicated correctly.
12. Validate revid and HLV of local and remote doc.

## #9 test_conflict_case_3

### Description

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

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['conflict_3']
	* continuous: False
   * conflict_resolver: remote-wins
6. Wait until the replicator is stopped.  
7. Check that the doc is replicated correctly.
8. Validate revid and HLV of local and remote doc.
9. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_3']
	* continuous: False
10. Wait until the replicator is stopped.  
11. Check that the doc is replicated correctly.
12. Validate revid and HLV of local and remote doc.

## #10 test_conflict_case_4

### Description

Bidirectional replication conflict between pre-upgrade CBL and SGW mutations,
resolved by the default conflict resolver where CBL wins — SGW and CBL have
conflicting legacy revisions, with CBL chosen as the winner under the legacy
default conflict resolution. CBL will rewrite the local winning revision
as a child of the remote revision and push it to SGW.

+------------------+--------------------------------------+--------------------------------------+
|                  |              CBL                     |                 SGW                  |
|                  +---------------+----------------------+---------------+----------------------+
|                  |   Rev Tree    |         HLV          |   Rev Tree    |         HLV          |
+------------------+---------------+----------------------+---------------+----------------------+
| Initial State    |     3-def     |      none            |     3-abc     |      none            |
| Expected Result  |      none     | [100@CBL1, 3abc@RTE] |     4-def     | [100@CBL1, 3abc@RTE] |
+------------------+---------------+----------------------+---------------+----------------------+

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['conflict_4']
	* continuous: False
   * conflict_resolver: local-wins
6. Wait until the replicator is stopped.  
7. Validate revid and HLV of local and remote doc.
8. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_4']
	* continuous: False
9. Wait until the replicator is stopped.  
10. Check that the doc is replicated correctly.
11. Validate revid and HLV of local and remote doc.

## #11 test_conflict_case_5

### Description

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

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['conflict_5']
	* continuous: False
   * conflict_resolver: local-wins
6. Wait until the replicator is stopped.  
7. Validate revid and HLV of local and remote doc.
8. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_5']
	* continuous: False
9. Wait until the replicator is stopped.  
10. Check that the doc is replicated correctly.
11. Validate revid and HLV of local and remote doc.

## #12 test_conflict_case_6

### Description

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

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['conflict_6']
	* continuous: False
   * conflict_resolver: local-wins
6. Wait until the replicator is stopped.  
7. Validate revid and HLV of local and remote doc.
8. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_6']
	* continuous: False
9. Wait until the replicator is stopped.  
10. Check that the doc is replicated correctly.
11. Validate revid and HLV of local and remote doc.

## #13 test_conflict_case_7

### Description

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

### Steps

1. Delete Sync Gateway 'upgrade' database if exists.
2. Restore Couchbase Server Bucket using `upgrade` dataset.
3. Wait 2s to ensure SG picks up the restored database.
4. Reset local database, and load `upgrade` dataset.
5. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: pull
	* document_ids: ['conflict_6']
	* continuous: False
   * conflict_resolver: local-wins
6. Wait until the replicator is stopped.  
7. Validate revid and HLV of local and remote doc.
8. Start a replicator:
	* endpoint: '/upgrade'
	* collections : '_default._default'
	* type: push
	* document_ids: ['conflict_6']
	* continuous: False
9. Wait until the replicator is stopped.  
10. Validate revid and HLV of local and remote doc.