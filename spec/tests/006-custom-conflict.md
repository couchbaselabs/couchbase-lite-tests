# Test Cases

## #1 test_custom_conflict_local_wins

### Description

Test that the custom conflict resolver functions properly when it is
set up to always return the local document.

### Steps

1. Reset SG and load `names` dataset.
2. Reset empty local database
3. Start a replicator: 
    * endpoint: `/names`
    * collections : `_default._default`
    * type: pull
    * continuous: false
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that all docs are replicated correctly.
6. Modify the local name_101 document `name.last` = 'Smith'
7. Modify the remote name_101 document `name.last` = 'Jones'
8. Start a replicator:
    * endpoint: `/names`
    * collections : `_default._default`
    * type: push/pull
    * continuous: false
    * credentials: user1/pass
    * conflictResolver: 'local-wins'
9. Wait until the replicator is stopped.
10. Check that the name_101 document `name.last` == 'Smith'