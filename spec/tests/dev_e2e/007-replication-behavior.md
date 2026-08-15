# Test Cases

## test_pull_empty_database_active_only

### Description

Test that in the presence of server side deletions, only non deleted items get replicated to an empty
local side database.  In otherwords, activeOnly should be activated in this scenario.

### Steps

1. Reset SG and load `names` dataset
2. Delete name_101 through name_150 on sync gateway
3. Reset local database and load `empty` dataset.
4.  Start a replicator:
        * endpoint: `/names`
        * collections : `_default._default`
        * type: pull
        * continuous: false
        * credentials: user1/pass
        * enable_document_listener: true
5. Wait until the replicator is stopped.
6. Check that only the 50 non deleted documents were replicated

## test_pull_resurrected_doc

### Description

Pulling Resurrected Document from SGW Without Conflict.

Test verifies that when a document is deleted locally (and synced as a tombstone) 
and later resurrected directly in Couchbase Server (CBS), the client successfully
pulls the resurrected document without generating a conflict.

### Steps

1. Reset SG and load `names` dataset.
2. Reset local database and load `names` dataset.
3. Start a replicator:
    * endpoint: `/names`
    * collections : `_default._default`
    * type: push
    * continuous: false
    * credentials: user1/pass
    * enable_document_listener: true
4. Wait until the replicator is stopped.
5. Delete `name_50` in the local database.
6. Assert `name_50` is `deleted`
7. Start a replicator:
    * endpoint: `/names`
    * collections : `_default._default`
    * type: push
    * continuous: false
    * credentials: user1/pass
    * enable_document_listener: true
8. Wait until the replicator is stopped.
9. Resurrect `name_50` in CBS
10. Start a replicator:
    * endpoint: `/names`
    * collections : `_default._default`
    * type: pull
    * continuous: false
    * credentials: user1/pass
    * enable_document_listener: true
11. Wait until the replicator is stopped.
12. Check `name_50` is not `deleted`