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
    * type: pull
    * continuous: false
    * credentials: user1/pass
    * conflictResolver: 'local-wins'
9. Wait until the replicator is stopped.
10. Check that the name_101 document `name.last` == 'Smith'
11. Start a replicator:
    * endpoint: `/names`
    * collections : `_default._default`
    * type: push
    * continuous: false
    * credentials: user1/pass
    * conflictResolver: 'local-wins'
12. Wait until the replicator is stopped.
13. Check that all docs are replicated correctly.


## #2 test_custom_conflict_remote_wins

### Description

Test that the custom conflict resolver functions properly when it is
set up to always return the remote document.

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
    * type: pull
    * continuous: false
    * credentials: user1/pass
    * conflictResolver: 'remote-wins'
9. Wait until the replicator is stopped.
10. Check that the name_101 document `name.last` == 'Jones'
11. Start a replicator:
    * endpoint: `/names`
    * collections : `_default._default`
    * type: push
    * continuous: false
    * credentials: user1/pass
    * conflictResolver: 'local-wins'
12. Wait until the replicator is stopped.
13. Check that all docs are replicated correctly.


## #3 test_custom_conflict_delete

### Description

Test that the custom conflict resolver functions properly when it is
set up to always return a deletion

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
    * type: pull
    * continuous: false
    * credentials: user1/pass
    * conflictResolver: 'delete'
9. Wait until the replicator is stopped.
10. Check that the name_101 document doesn't exist
11. Start a replicator:
    * endpoint: `/names`
    * collections : `_default._default`
    * type: push
    * continuous: false
    * credentials: user1/pass
    * conflictResolver: 'local-wins'
12. Wait until the replicator is stopped.
13. Check that all docs are replicated correctly.

## #4 test_custom_conflict_merge

### Description

Test that the custom conflict resolver functions properly when it is
set up to merge the "name" property

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
    * type: pull
    * continuous: false
    * credentials: user1/pass
    * conflictResolver: 'merge' / {'property': 'name'}
9. Wait until the replicator is stopped.
10. Check that the name_101 document `name` property contains `[{'first': 'Davis', 'last': 'Smith'},{'first': 'Davis', 'last': 'Jones'}]
11. Start a replicator:
    * endpoint: `/names`
    * collections : `_default._default`
    * type: push
    * continuous: false
    * credentials: user1/pass
    * conflictResolver: 'local-wins'
12. Wait until the replicator is stopped.
13. Check that all docs are replicated correctly.