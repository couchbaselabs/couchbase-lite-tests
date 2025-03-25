# Test Cases

## test_remove_docs_from_channel_with_auto_purge_enabled

### Description

Test that the replicator will purged the docs that the user lost the access to by removing the docs from all user's channels.

### Steps

1. Reset SG and load `posts` dataset.
2. Reset local database and load `posts` dataset.
3. Start a replicator:
    * endpoint: `/posts`
    * collections :
      * `_default_.posts`
    * type: pull
    * continuous: false
    * autoPurge: true
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Verify that the all the docs to which the user has access were pulled.
6. Update docs on SG:
   * Update `post_1` with channels = [] (ACCESS-REMOVED)
   * Update `post_2` with channels = ["group1"]
   * Update `post_3` with channels = ["group2"]
   * Delete `post_4`
7. Start another replicator with the same config as above
8. Wait until the replicator stops.
9. Check the local documents:
   * `post_1` was purged.
   * `post_2` and `post_3` were updated with the new channels.
   * `post_4` was deleted.
10. Check document replications:
   * `post_1` has access-removed flag set.
   * `post_2` and `post_3` have no flags set.
   * `post_4` has deleted flag set.

## test_revoke_access_with_auto_purge_enabled

### Description

Test that the replicator will purged the docs that the user lost the access to by revoking the access to all of the user's channels that the docs are in.

1. Reset SG and load `posts` dataset.
2. Reset local database and load `posts` dataset.
3. Start a replicator:
    * endpoint: `/posts`
    * collections :
      * `_default_.posts`
    * type: pull
    * continuous: false
    * autoPurge: true
    * credentials: user1/pass
4. Wait until the replicator stops.
5. Verify that the all the docs to which the user has access were pulled.
6. Update user1's access to channels on SG:
    * Remove access to `group2` channel.
7. Start another replicator with the same config as above
8. Wait until the replicator stops.
9. Check local documents:
   * `post_4` and `post_5` were purged.
10. Check document replications:
   * `post_4` and `post_5` have access-removed flag set.
11. Restore user1's access to channels on SG:
    * Add user access to `group2` channel back again.
12. Start another replicator with the same config as above.
13. Wait until the replicator stops.
14. Check local documents:
    * `post_4` and `post_5` are back.
15. Check document replications:
    * `post_4` and `post_5` have events with no flags set.

## test_remove_docs_from_channel_with_auto_purge_disabled

### Description

Test that when auto-purge is disabled, the replicator will not purge the docs that the user lost the access to from removing the docs from all user's channels.

**Notes**
* The document replication events for the removed-access docs should have the access-removed flag set.

### Steps

1. Reset SG and load `posts` dataset.
2. Reset local database and load `posts` dataset.
3. Start a replicator:
   * endpoint: `/posts`
   * collections :
      * `_default_.posts`
   * type: pull
   * continuous: false
   * autoPurge: false
   * credentials: user1/pass
4. Wait until the replicator stops.
5. Verify that the all the docs to which the user has access were pulled.
6. Snapshot the database
7. Update docs on SG:
   * Update `post_1` with channels = [] (ACCESS-REMOVED)
   * Update `post_2` with channels = ["group1"]
   * Update `post_3` with channels = ["group2"]
8. Start a continuous replicator with a config similar to the one above
9. Check document replications:
   * `post_1` has access-removed flag set.
   * `post_2` and `post_3` have no flags set.
10. Check local documents:
   * there are 5 documents in the database
   * `post_1`, `post_2` and `post_3` are updated with new channels.
   * `post_4` and `post_5` are unchanged

## test_revoke_access_with_auto_purge_disabled

### Description

Test that when auto-purge is disabled, the replicator will not purge the docs that the user lost the access to by revoking the access to all of the user's channels that the docs are in.

**Notes**
* The document replication events for the removed-access docs should have the access-removed flag set.
* For the removed-access docs from the access revoked (no changes in their properties), if there is a pull filter set, the pull filter will not be called for those removed-access docs as auto-purge is disabled.

1. Reset SG and load `posts` dataset.
2. Reset local database and load `posts` dataset.
3. Start a replicator:
   * endpoint: `/posts`
   * collections :
      * `_default_.posts`
   * type: pull
   * continuous: false
   * autoPurge: false
   * credentials: user1/pass
3. Wait until the replicator stops.
4. Verify that the all the docs to which the user has access were pulled.
5. Update user1's access to channels on SG:
   * Remove access to `group2` channel.
6. Start the replicator with the same config as the step 3.
7. Start another replicator:
   * endpoint: `/posts`
   * collections :
      * `_default_.posts`
   * type: pull
   * continuous: true
   * autoPurge: false
   * credentials: user1/pass
8. Wait until the replicator is stopped.
9. Check document replications (NEED REST API):
    * `post_4` and `post_5` have access-removed flag set
10. Check local documents:
   * `post_4` and `post_5` were not purged.

## test_filter_removed_access_documents

### Description

Test that when the removed access documents are filtered, the removed access documents are not be purged.

### Steps

1. Reset SG and load `posts` dataset.
2. Reset local database and load `posts` dataset.
3. Start a replicator:
   * endpoint: `/posts`
   * collections :
      * `_default_.posts`
   * type: pull
   * continuous: false
   * autoPurge: true
   * credentials: user1/pass
4. Wait until the replicator stops.
5. Verify that the all the docs to which the user has access were pulled.
6. Snapshot the database
7. Update docs on SG:
   * Update `post_1` with channels = [] (ACCESS-REMOVED)
   * Update `post_2` with channels = [] (ACCESS-REMOVED)
7. Start another replicator:
   * endpoint: `/posts`
   * collections :
      * `_default_.posts`
      * pullFilter: name: documentIDs, params: {"documentIDs": {"_default.posts": ["post_1"]}} }
   * type: pull
   * continuous: true
   * autoPurge: true
   * credentials: user1/pass
8. Check document replications:
   * `post_1` has access-removed flag set with no error.
   * `post_2` has access-removed flag set with WebSocket/403 ("CBL, 10403) error.
9. Check local documents:
   * `post_1` was purged.
   * `post_2` still exists.

## test_remove_user_from_role

### Description

Test that the replicator will purge the docs that the user lost the access to when the user loses access 
to a channel.

### Steps

- `auto_purge_enabled`: [true, false]

1. Reset SG and load `posts` dataset.
2. Reset local database and load `posts` dataset.
3. Start a replicator:
    * endpoint: `/posts`
    * collections :
      * `_default_.posts`
    * type: pull
    * continuous: false
    * autoPurge: `auto_purge_enabled`
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Verify that the all the docs to which the user has access were pulled.
6. Update user by removing `group2` from the `admin_channels` property.
7. Start another replicator with the same config as above
8. Wait until the replicator stops.
9. Check the local documents:
   * `post_1`, `post_2` and `post_3` are still present.
   * `post_4` and `post_5` were purged if `auto_purge_enabled` is true, still present otherwise.
10. Check document replications:
   * `post_4` and `post_5` have access-remove flag set

## test_remove_role_from_channel

### Description

Test that the replicator will purge the docs that the user lost the access to when the user's role
loses access to a channel

### Steps

- `auto_purge_enabled`: [true, false]

1. Reset SG and load `posts` dataset.
2. Reset local database and load `posts` dataset.
3. Add a role on Sync Gateway `role1` with access to channel `group3` in `_default.posts`
4. Update `user1` to be in `role1`
5. Add a document `post_6` on Sync Gateway to `posts`
    * title: Post 6
    * content: This is the content of my post 6
    * channels: ["group3"]
    * owner: user2
6. Start a replicator:
    * endpoint: `/posts`
    * collections :
      * `_default_.posts`
    * type: pull
    * continuous: false
    * autoPurge: `auto_purge_enabled`
    * credentials: user1/pass
7. Wait until the replicator is stopped.
8. Verify that the all the docs to which the user has access were pulled.
9.  Update `role1` by removing `group3` from the `admin_channels` property.
10. Start another replicator with the same config as above
11. Wait until the replicator stops.
12. Check the local documents:
   * `post_1`, `post_2`, `post_3`, `post_4` and `post_5` are still present.
   * `post_6` was purged if `auto_purge_enabled` is true, still present otherwise.
13. Check document replications:
   * `post_6` has access-remove flag set

## test_pull_after_restore_access

### Description

Test that restoring access to a document after its access was removed results in
the document being replicated again

### Steps

1. Reset SG and load `posts` dataset.
2. Reset local database and load `posts` dataset.
3. Start a replicator:
   * endpoint: `/posts`
   * collections :
      * `_default_.posts`
   * type: pull
   * continuous: false
   * autoPurge: true
   * credentials: user1/pass
4. Wait until the replicator stops.
5. Verify that the all the docs to which the user has access were pulled.
6. Start another replicator:
   * endpoint: `/posts`
   * collections :
      * `_default_.posts`
   * type: pull
   * continuous: true
   * credentials: user1/pass
   * enable_document_listener: True
7. Snapshot the database for `post_1`
8. Update doc in SGW:
   * Update `post_1` with channels = [] (ACCESS-REMOVED)
9. Wait for a document event regarding `post_1`
   * flags: access-removed
10. Check that `post_1` no longer exists locally
11. Update doc in SGW:
   * Update `post_1` with channels = ["group1"]
12. Wait for a document event regarding `post_1` with no error
13. Check that `post_1` exists locally

## test_push_after_remove_access

### Description

Test that removing user access to a document has no effect on the ability
of a user to push said document.

### Steps

1. Reset SG and load `posts` dataset.
2. Reset local database and load `posts` dataset.
3. Start a replicator:
   * endpoint: `/posts`
   * collections :
      * `_default_.posts`
   * type: pull
   * continuous: false
   * autoPurge: true
   * credentials: user1/pass
4. Wait until the replicator stops.
5. Verify that the all the docs to which the user has access were pulled.
6. Start another replicator:
   * endpoint: `/posts`
   * collections :
      * `_default_.posts`
   * type: push
   * continuous: true
   * credentials: user1/pass
   * enable_document_listener: True
7. Update doc in CBL:
   * Update `post_1` with channels = [] (ACCESS-REMOVED)
8. Wait for a document event regarding `post_1` with no error
9.  Update doc in CBL:
   * Update `post_1` with channels = ["fake"]
10. Wait for a document event regarding `post_1` with no error
11. Check that `post_1` on Sync Gateway has channels = ["fake"]

## test_auto_purge_after_resurrection

### Description

Test that if a doc is deleted / purged and then recreated auto purge will still
remove the doc if the user loses access.

### Steps

`remove_type` = [delete, purge]

1. Reset SG and load `posts` dataset.
2. Reset local database and load `posts` dataset.
3. Start a replicator:
   * endpoint: `/posts`
   * collections :
      * `_default_.posts`
   * type: pull
   * continuous: false
   * autoPurge: true
   * credentials: user1/pass
4. Wait until the replicator stops.
5. Verify that the all the docs to which the user has access were pulled.
6. Perform a `remove_type` operation to remove `post_1` on SGW
7. Recreate `post_1` on SGW with channels `[group1]`
8. Remove `user1` from `group1`
9. Snapshot the local db for post_1
10. Start a replicator identical to the previous
11. Wait until the replicator stops.
12. Check that `post_1` no longer exists