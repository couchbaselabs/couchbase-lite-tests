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