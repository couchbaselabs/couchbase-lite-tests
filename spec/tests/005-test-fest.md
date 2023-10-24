# Test Cases

## test_create_tasks

### Description

Test creating tasks.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

### Steps

1. Reset SG and load `todo` dataset.
2. Reset local database, and load `todo` dataset into database `db1` and `db2`.
3. Create SG role named `lists.user1.db1-list1.contributor`.
4. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
5. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
6. Snapshot documents in `db1`:
   * `_default.lists`.`db2-list1`
   * `_default.tasks`.`db2-list1-task1`
7. Snapshot documents in `db2`
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
8. Create a list and a task in `db1`:
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as 
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": true,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l1.jpg` blob.
9. Create a list and a task in `db2`:
   * Create SG role named `lists.user1.db2-list1.contributor`.
   * Create a list document in `_default.lists` as
      * { "_id": "db2-list1", "name": "db2 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db2-list1-task1", "name": "db2 list1 task1", "complete": true,  "image": null, taskList" : { "id" : "db2-list1", "owner" : "user1" } }
      * Set the `image` key with the `l2.jpg` blob.
10. Wait and check the pull document replication events in `db1`:
   * `_default.lists`.`db2-list1`
   * `_default.tasks`.`db2-list1-task1`
11. Wait and check the pull document replication events in `db2`:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
12. Verify the snapshot from step 5 by checking the content of the snapshot documents.
13. Verify the snapshot from step 6 by checking the content of the snapshot documents.

## test_update_task

### Description

Test updating tasks.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

### Steps

1. Reset SG and load `todo` dataset.
2. Reset local database, and load `todo` dataset into database `db1` and `db2`.
3. Create SG role named `lists.user1.db1-list1.contributor`.
4. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
5. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
5. Snapshot documents in `db2`:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
6. Create a list and a task in `db1`:
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l5.jpg` blob.
7. Wait and check the pull document replication events in `db2`:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
8. Verify the snapshot from step 5 by checking the content of the snapshot documents.
9. Snapshot documents in `db1`:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
10. Update the `db1-list1-task1` task in `db2`:
   * Set the `name` key with `Updated db1 list1 task1`.
   * Set the `complete` key with `true`.
   * Set the `image` key with the `l10.jpg` blob.
11. Wait and check the pull document replication events in `db1`:
   * `_default.tasks`.`db1-list1-task1`
12. Verify the snapshot from step 9:
   * Check that `_default.lists`.`db1-list1` has no changes.
   * Check the content of `_default.tasks`.`db1-list1-task1`.

## test_delete_task

### Description

Test deleting task.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

### Steps

1. Reset SG and load `todo` dataset.
2. Reset local database, and load `todo` dataset into database `db1` and `db2`.
3. Create SG role named `lists.user1.db1-list1.contributor`.
4. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
5. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
5. Create a list and a task in `db1`:
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l1.jpg` blob.
6: Snapshot docs in `db1`
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
7. Wait and check the pull document replication events in `db2`
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1` 
8: Snapshot docs in `dbr21`
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
9. Delete the `_default.tasks`.`db1-list1-task1` task in `db1`
10. Wait and check the pull deleted document replication event in `db2`
   * `_default.tasks`.`db1-list1-task1` (Deleted)
11. Check that `_default.tasks`.`db1-list1-task1` was deleted from `db1`.
12. Check that `_default.tasks`.`db1-list1-task1` was deleted from `db2`.

## test_delete_list

### Description

Test deleting list and its tasks.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

### Steps

1. Reset SG and load `todo` dataset.
2. Reset local database, and load `todo` dataset into database `db1` and `db2`.
3. Create SG role named `lists.user1.db1-list1.contributor`.
4. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
5. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
5. Create a list and two tasks in `db1`:
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l5.jpg` blob.
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task2", "name": "db1 list1 task2", "complete": true,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
6: Snapshot docs in `db1`
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
7. Wait and check the pull document replication events in `db2`
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
8: Snapshot docs in `db2`
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
9. Delete the list and its tasks from `db1`.
   * Delete `_default.lists`.`db1-list1`
   * Delete `_default.tasks`.`db1-list1-task1`
   * Delete `_default.tasks`.`db1-list1-task2`
10. Wait and check the pull document replication events in `db2`.
   * `_default.lists`.`db1-list1` (deleted)
   * `_default.tasks`.`db1-list1-task1` (deleted)
   * `_default.tasks`.`db1-list1-task2` (deleted)
11. Check that the list and two tasks are deleted from `db1`.
12. Check that the list and two tasks are deleted from `db2`.

## test_create_tasks_two_users

### Description

Test creating tasks with two users without sharing.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

### Steps

1. Reset SG and load `todo` dataset.
2. Reset local database, and load `todo` dataset into database `db1` and `db2`.
3. Create SG role named `lists.user1.db1-list1.contributor`.
4. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
5. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user2/pass
5. Create a list and a task in `db1`:
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l1.jpg` blob.
6. Create a list and a task in `db2`:
   * Create SG role named `lists.user2.db2-list1.contributor`.
   * Create a list document in `_default.lists` as
      * { "_id": "db2-list1", "name": "db2 list1", "owner": "user2" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db2-list1-task1", "name": "db2 list1 task1", "complete": true,  "image": null, "taskList" : { "id" : "db2-list1", "owner" : "user2" } }
      * Set the `image` key with the `l2.jpg` blob.
7. Wait for 10 seconds which should be enough for the two replicators to finish replicating.
8. Check that no document replication events are in `db1`.
9. Check that no document replication events are in `db2`.
10. Check that `db1` has only `_default.lists`.`db1-list1` and `_default.tasks`.`db1-list1-task1`.
11. Check that `db2` has only `_default.lists`.`db2-list1` and `_default.tasks`.`db2-list1-task1`.

## test_share_list

### Description

Test sharing a list and its tasks to a user.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

1. Reset SG and load `todo` dataset.
2. Reset local database, and load `todo` dataset into database `db1` and `db2`.
3. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
4. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user2/pass
5. Create a list and 2 tasks in `db1:
   * Create SG role named `lists.user1.db1-list1.contributor`.
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l1.jpg` blob.
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task2", "name": "db1 list1 task2", "complete": true,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
6. Wait for 10 seconds which should be enough for the two replicators to finish replicating.
7. Check that no document replication events are in `db2`.
8. Snapshot documents in `db2`:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
9. Creating a user document in the `_default.users` to share the `_default.lists`.`db1-list1` list in `db1` as
   * { "_id": "db1-list1-user2", "username": "user2", "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
10. Wait and check the pull document replication events in `db2`.
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
11. Verify snapshot from step 8 to check the content of the snapshot documents.
12. Check that no `_default.users`.`db1-list1-user2` document is in `db2`.

## test_update_shared_tasks

Test updating shared tasks.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

1. Reset SG and load `todo` dataset.
2. Reset local database, and load `todo` dataset into database `db1` and `db2`.
3. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
4. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user2/pass
5. Create a list and 2 tasks in `db1`:
   * Create SG role named `lists.user1.db1-list1.contributor`.
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l1.jpg` blob.
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task2", "name": "db1 list1 task2", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `s1.jpg` blob.
6. Wait for 10 seconds which should be enough for the two replicators to finish replicating.
7. Check that no document replication events are in `db2`.
8. Snapshot documents in `db2`:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
9. Creating a user document in the `_default.users` to share the `_default.lists`.`db1-list1` list in `db1` as
   * { "_id": "db1-list1-user2", "username": "user2", "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
10. Wait and check the pull document replication events in `db2`.
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
11. Verify snapshot from step 8 to check the content of the snapshot documents.
12. Check that no `_default.users`.`db1-list1-user2` document is in `db2`
13. Snapshot documents in `db1`:
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
14. Update `_default.tasks`.`db1-list1-task1` in `db2`:
   * Set the `name` key with `Updated db1 list1 task1`.
   * Set the `complete` key with `true`.
   * Set the `image` key with the `s1.jpg` blob.
15. Delete `_default.tasks`.`db1-list1-task2` in `db2`
16. Wait and check the pull replication events in `db1`:
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2` (deleted)
17. Verify snapshot from step 12:
   * Check the updated content of `_default.tasks`.`db1-list1-task1` document
   * Check that the `_default.tasks`.`db1-list1-task2` document was deleted.

## test_unshare_list

Test unsharing a list. The shared list and tasks will be purged from the unshared user's database.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

1. Reset SG and load `todo` dataset.
2. Reset local database, and load `todo` dataset into database `db1` and `db2`.
3. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
4. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user2/pass
5. Create a list and 2 tasks in `db1` as separate steps.
   * Create SG role named `lists.user1.db1-list1.contributor`.
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l1.jpg` blob.
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task2", "name": "db1 list1 task2", "complete": true,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `s1.jpg` blob.
6. Wait for 10 seconds which should be enough for the two replicators to finish replicating.
7. Check that no document replication events are in `db2`.
8. Snapshot documents in `db2`:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
9. Creating a user document in the `_default.users` to share the `_default.lists`.`db1-list1` list in `db1` as
   * { "_id": "db1-list1-user2", "username": "user2", "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
10. Wait and check the pull document replication events in `db2`.
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
11. Verify snapshot from step 8 to check the content of the snapshot documents.
12. Check that no `_default.users`.`db1-list1-user2` document is in `db2`
13. Unshare the `db1-list1` list by deleting `_default.users`.`db1-list1-user2` from `db1`.
14. Wait and check the document replication events in `db1`.
   * `_default.users`.`db1-list1-user2` (deleted, pushed)
15. Wait and check the document replication events in `db2`.
   * `_default.lists`.`db1-list1` (pull, purged)
   * `_default.tasks`.`db1-list1-task1` (pull, purged)
   * `_default.tasks`.`db1-list1-task2` (pull, purged)
16. Check that the shared list and its tasks do not exist in `db2`.
