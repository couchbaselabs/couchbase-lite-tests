# Test Cases

## test_create_tasks

### Description

Test creating tasks.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

### Steps

1. Setup test env and assign SG roles to users:
   * Reset SG and load `todo` dataset.
   * Reset local database, and load `todo` dataset into database `db1` and `db2`.
   * Assign SG roles to users:
      * user1 : `lists.user1.db1-list1.contributor`, `lists.user1.db2-list1.contributor`
2. Snapshot db1:
   * `_default.lists`.`db2-list1`
   * `_default.tasks`.`db2-list1-task1`
3. Snapshot db2:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
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
6. Create a list and a task in db1:
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as 
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": true,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l1.jpg` blob.
7. Create a list and a task in db2:
   * Create a list document in `_default.lists` as
      * { "_id": "db2-list1", "name": "db2 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db2-list1-task1", "name": "db2 list1 task1", "complete": true,  "image": null, taskList" : { "id" : "db2-list1", "owner" : "user1" } }
      * Set the `image` key with the `l2.jpg` blob.
8. Wait for the new docs to be pulled to db1:
   * `_default.lists`.`db2-list1`
   * `_default.tasks`.`db2-list1-task1`
9. Wait for the new docs to be pulled to db2:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
10. Verify that the new docs are in db1.
11. Verify that the new docs are in db2.

## test_update_task

### Description

Test updating tasks.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

### Steps

1. Setup test env and assign SG roles to users:
   * Reset SG and load `todo` dataset.
   * Reset local database, and load `todo` dataset into database `db1` and `db2`.
   * Assign SG roles to users:
   *  user1 : `lists.user1.db1-list1.contributor`
2. Snapshot db2:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
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
   * credentials: user1/pass
5. Create a list and a task in db1:
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l5.jpg` blob.
6. Wait for the new docs to be pulled to db2:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
7. Verify that the new docs are in db2:
8. Snapshot db1:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
9. Update the db1-list1-task1 task in db2:
   * Set the `name` key with `Updated db1 list1 task1`.
   * Set the `complete` key with `true`.
   * Set the `image` key with the `l10.jpg` blob.
10. Wait for the new doc to be pulled to db1:
   * `_default.tasks`.`db1-list1-task1`
11. Verify that the doc has been updated in db1:
   * Check that `_default.lists`.`db1-list1` has no changes.
   * Check the content of `_default.tasks`.`db1-list1-task1`.

## test_delete_task

### Description

Test deleting task.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

### Steps

1. Setup test env and assign SG roles to users:
   * Reset SG and load `todo` dataset.
   * Reset local database, and load `todo` dataset into database `db1` and `db2`.
   * Assign SG roles to users:
      * user1 : `lists.user1.db1-list1.contributor`
2. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
3. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
4. Create a list and a task in db1:
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l1.jpg` blob.
5. Wait for the updated doc to be pulled to db2:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1` 
6. Snapshot documents in db1:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
7. Snapshot documents in db2:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
8. Delete the task _default.tasks.db1-list1-task1 in db1.
9. Wait for the deleted document to be pulled to db2:
   * `_default.tasks`.`db1-list1-task1` (Deleted)
10. Verify that _default.tasks.db1-list1-task1 was deleted from db1.
11. Verify that _default.tasks.db1-list1-task1 was deleted from db2.

## test_delete_list

### Description

Test deleting list and its tasks.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

### Steps

1. Setup test env and assign SG roles to users:
   * Reset SG and load `todo` dataset.
   * Reset local database, and load `todo` dataset into database `db1` and `db2`.
   * Assign SG roles to users:
      * user1 : `lists.user1.db1-list1.contributor`
2. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
3. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
4. Create a list and two tasks in db1:
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `s1.jpg` blob.
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task2", "name": "db1 list1 task2", "complete": true,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
5. Snapshot documents in db1:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
6. Snapshot documents in `db2`:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
7. Delete the the list1 and the two tasks in db1.
   * Delete `_default.lists`.`db1-list1`
   * Delete `_default.tasks`.`db1-list1-task1`
   * Delete `_default.tasks`.`db1-list1-task2`
8. Wait for the deleted documents to be pulled to db2.
   * `_default.lists`.`db1-list1` (deleted)
   * `_default.tasks`.`db1-list1-task1` (deleted)
   * `_default.tasks`.`db1-list1-task2` (deleted)
9. Verify that the list and two tasks were deleted from db1.
10. Verify that the list and two tasks were deleted from db2.

## test_create_tasks_two_users

### Description

Test creating tasks with two users without sharing.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

### Steps

1. Setup test env and assign SG roles to users:
   * Reset SG and load `todo` dataset.
   * Reset local database, and load `todo` dataset into database `db1` and `db2`.
   * Assign SG roles to users:
      * user1 : `lists.user1.db1-list1.contributor`
      * user2 : `lists.user1.db2-list1.contributor`
2. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
3. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user2/pass
4. Create a list and a task in db1:
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l1.jpg` blob.
7. Snapshot documents in db1:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.lists`.`db2-list1`
   * `_default.tasks`.`db2-list1-task1`
8. Create a list and a task in db2:
   * Create SG role named `lists.user2.db2-list1.contributor`.
   * Create a list document in `_default.lists` as
      * { "_id": "db2-list1", "name": "db2 list1", "owner": "user2" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db2-list1-task1", "name": "db2 list1 task1", "complete": true,  "image": null, "taskList" : { "id" : "db2-list1", "owner" : "user2" } }
      * Set the `image` key with the `l2.jpg` blob.
9. Snapshot documents in db2:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.lists`.`db2-list1`
   * `_default.tasks`.`db2-list1-task1` 
10. Verify that there are no document replication events in db1, for 10 seconds.
11. Verify that there are no document replication events in db2, for 10 seconds.
12. Verify that db1 has not changed.
13. Verify that db2 has not changed.

## test_share_list

### Description

Test sharing a list and its tasks to a user.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

1. Setup test env and assign SG roles to users:
   * Reset SG and load `todo` dataset.
   * Reset local database, and load `todo` dataset into database `db1` and `db2`.
   * Assign SG roles to users:
      * user1 : `lists.user1.db1-list1.contributor`
2. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
3. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user2/pass
4. Snapshot documents in db2:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
5. Create a list and two tasks in db1:
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l1.jpg` blob.
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task2", "name": "db1 list1 task2", "complete": true,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
6. Verify that there are no document replication events in db2, for 10 seconds.
7. Verify that there are no new documents in db2.
8. Create a user document to share the _default.lists.db1-list1 from db1:
   * { "_id": "db1-list1-user2", "username": "user2", "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
9. Wait for the the newly visible documents to be pulled to db2:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
10. Verify snapshot that the new docs are in db2 and that _default.users.db1-list1-user2 is not.

## test_update_shared_tasks

Test updating shared tasks.

This test will use two databases either on the same test server or on two test servers depending on the availability of the test servers.

1. Setup test env and assign SG roles to users:
   * Reset SG and load `todo` dataset.
   * Reset local database, and load `todo` dataset into database `db1` and `db2`.
   * Assign SG roles to users:
      * user1 : `lists.user1.db1-list1.contributor`
2. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
3. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user2/pass
4. Snapshot documents in db2:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
   * `_default.users`.`db1-list1-user2`
5. Create a list and two tasks in db1:
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l1.jpg` blob.
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task2", "name": "db1 list1 task2", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `s1.jpg` blob.
6. Snapshot documents in db1:
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
7. Verify that there are no document replication events in db2, for 10 seconds.
8. Create a user document to share the _default.lists.db1-list1 from db1:
   * { "_id": "db1-list1-user2", "username": "user2", "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
9. Wait for the newly visible docs to be pulled to db2:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
10. Verify that the newly visible docs are in db2 and that _default.users.db1-list1-user2 is not.
11. Update _default.tasks.db1-list1-task1 and delete db1-list1-task2 in db2:
   * Set the `name` key with `Updated db1 list1 task1`.
   * Set the `complete` key with `true`.
   * Set the `image` key with the `s1.jpg` blob.
   * Delete `_default.tasks`.`db1-list1-task2` in `db2`
12. Wait for the changes to be pulled to db1:
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2` (deleted)
13. Verify that the new docs are in db1:
   * Check the updated content of `_default.tasks`.`db1-list1-task1` document
   * Check that the `_default.tasks`.`db1-list1-task2` document was deleted.

## test_unshare_list

Test unsharing a list. The shared list and tasks will be purged from the unshared user's database.

This test will use two databases either on the same test server or on two test servers depending on 
the availability of the test servers.

1. Setup test env and assign SG roles to users:
   * Reset SG and load `todo` dataset.
   * Reset local database, and load `todo` dataset into database `db1` and `db2`.
   * Assign SG roles to users:
      * user1 : `lists.user1.db1-list1.contributor`
2. Start a replicator:
   * endpoint: `/todo`
   * database: `db1`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user1/pass
3. Start a replicator:
   * endpoint: `/todo`
   * database: `db2`
   * collections : `_default.lists`, `_default.tasks`, `_default.users`
   * type: push-and-pull
   * continuous: true
   * enableDocumentListener: true
   * credentials: user2/pass
4. Snapshot documents in db2:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
   * `_default.users`.`db1-list1-user2`
5. Create a list and two tasks in db1:
   * Create a list document in `_default.lists` as
      * { "_id": "db1-list1", "name": "db1 list1", "owner": "user1" }
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task1", "name": "db1 list1 task1", "complete": false,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `l1.jpg` blob.
   * Create a task document in `_default.tasks` as  
      * { "_id": "db1-list1-task2", "name": "db1 list1 task2", "complete": true,  "image": null, "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
      * Set the `image` key with the `s1.jpg` blob.
6. Verify that there are no document replication events in db1, for 10 seconds.
7. Create a user document to share the _default.lists.db1-list1 from db1:
   * { "_id": "db1-list1-user2", "username": "user2", "taskList" : { "id" : "db1-list1", "owner" : "user1" } }
8. Wait for the newly visible documents to be pulled to db2:
   * `_default.lists`.`db1-list1`
   * `_default.tasks`.`db1-list1-task1`
   * `_default.tasks`.`db1-list1-task2`
9. Verify that the newly visible docs are in db2 and that _default.users.db1-list1-user2 is not.
10. Unshare the db1-list1 list by deleting _default.users.db1-list1-user2 from db1.
11. Verify that the deletion is pushed from db1.
12. Wait for the newly invisible documents to be removed from db2:
   * `_default.lists`.`db1-list1` (pull, acccessed_removed)
   * `_default.tasks`.`db1-list1-task1` (pull, accessed_removed)
   * `_default.tasks`.`db1-list1-task2` (pull, access_removed)
13. Verify that the shared list and its tasks do not exist in db2:
   * `_default.lists`.`db1-list1` (pull, purged)
   * `_default.tasks`.`db1-list1-task1` (pull, purged)
   * `_default.tasks`.`db1-list1-task2` (pull, purged)
   