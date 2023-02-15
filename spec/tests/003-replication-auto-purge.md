# Test Cases

## test_remove_docs_from_channel_with_auto_purge_enabled

### Description

Test that the replicator will purged the docs that the user lost the access to by removing the docs from all user's channels.

### Steps

1. Load `posts` dataset into a database.
2. Start a replicator: 
    * collections : 
      * `_default_.posts`
    * endpoint: `/posts`
    * type: pull
    * continuos: false
    * autoPurge: true
3. Wait until the replicator is stopped.
4. Check that the docs that the user has access to are all pulled.
5. Update docs on SG:
   * Update `post_1` by removing the user's `username` and `public` from the `channels` property (ACCESS-REMOVED)
   * Update `post_2` by removing only `public` from the `channels` property.
   * Update `post_3` by removing only the user's `username` from the `channels` property.
   * Delete `post_4`
6. Start the replicator with the same config as the step 2.
7. Wait until the replicator is stopped.
8. Check local documents:
   * `post_1` was purged.
   * `post_2` and `post_3` were updated with the new channels.
   * `post_4` was deleted.
9. Check document replications:
   * `post_1` has access-removed flag set.
   * `post_2` and `post_3` have no flags set.
   * `post_4` has deleted flag set.

## test_revoke_access_with_auto_purge_enabled

### Description

Test that the replicator will purged the docs that the user lost the access to by revoking the access to all of the user's channels that the docs are in.

1. Load `posts` dataset into a database.
2. Start a replicator: 
    * collections : 
      * `_default_.posts`
    * endpoint: `/posts`
    * type: pull
    * continuos: false
    * autoPurge: true
3. Wait until the replicator is stopped.
4. Check that the docs that the user has access to are all pulled.
5. Update user access to channels on SG:
    * Remove access to `public` channel.
6. Start the replicator with the same config as the step 2.
7. Wait until the replicator is stopped.
8. Check local documents:
   * `post_4` and `post_5` were purged.
   * `post_1`, `post_2`, and `post_3` have no changes.
9. Check document replications:
   * `post_4` and `post_5` have access-removed flag set.
   * `post_1`, `post_2`, and `post_3` have no document replication events.
10. Update user access to channels on SG:
    * Remove access to the user's `username` channel.
11. Start the replicator with the same config as the step 2.
12. Check local documents:
    * `post_1`, `post_2` and `post_3` were purged.
13. Check document replications:
    * `post_1`, `post_2`, and `post_3` have access-removed flag set.
14. Update user access to channels on SG:
    * Add user access to `public` channel back again.
16. Start the replicator with the same config as the step 2.
17. Wait until the replicator is stopped.
18. Check local documents:
    * `post_4` and `post_5` are pulled back.
    * `post_1`, `post_2` and `post_3` still doesn't exist.
19. Check document replications:
    * `post_4` and `post_5` have events with no flags set.
    * `post_1`, `post_2`, and `post_3` have no document replication events.
   
## test_remove_docs_from_channel_with_auto_purge_diabled

### Description

Test that when auto-purge is disabled, the replicator will not purge the docs that the user lost the access to from removing the docs from all user's channels.

**Notes**
* The document replication events for the removed-access docs should have the access-removed flag set.

### Steps

1. Load `posts` dataset into a database.
2. Start a replicator: 
   * collections : 
      * `_default_.posts`
   * endpoint: `/posts`
   * type: pull
   * continuos: false
   * autoPurge: false
3. Wait until the replicator is stopped.
4. Check that the docs that the user has access to are all pulled.
5. Update docs on SG:
   * Update `post_1` by removing the user's `username` and `public` from the `channels` property.
   * Update `post_2` by removing only `public` from the `channels` property.
   * Update `post_3` by removing only the user's `username` from the `channels` property.
6. Start the replicator with the same config as the step 2.
7. Wait until the replicator is stopped.
8. Check local documents:
   * `post_1`, `post_2` and `post_3` are updated with the new channels.
9. Check document replications:
   * `post_1` has access-removed flag set.
   * `post_2` and `post_3` have no flags set.

## test_revoke_access_with_auto_purge_disabled

### Description

Test that when auto-purge is disabled, the replicator will not purge the docs that the user lost the access to by revoking the access to all of the user's channels that the docs are in.

**Notes**
* The document replication events for the removed-access docs should have the access-removed flag set.
* For the removed-access docs from the access revoked (no changes in their properties), if there is a pull filter set, the pull filter will not be called for those removed-access docs as auto-purge is disabled. 

1. Load `posts` dataset into a database.
2. Start a replicator: 
   * collections : 
      * `_default_.posts`
   * endpoint: `/posts`
   * type: pull
   * continuos: false
   * autoPurge: false
3. Wait until the replicator is stopped.
4. Check that the docs that the user has access to are all pulled.
5. Update user access to channels on SG:
   * Remove access to `public` channel.
6. Start the replicator with the same config as the step 2.
7. Start a replicator: 
   * collections : 
      * `_default_.posts`
      * pullFilter:
         name: documentIDs
         params : { "documentIDs": ["post_4"] }
   * endpoint: `/posts`
   * type: pull
   * continuos: false
   * autoPurge: false    
8. Wait until the replicator is stopped.
9. Check local documents:
   * `post_4` and `post_5` are not purged.
10. Check document replications:
    * `post_4` and `post_5` have access-removed flag set but no errors (When a change was reject by the filter, the document replication will have WebSocket/403 error)

## test_filter_removed_access_documents

### Description

Test that when the removed access documents are filtered, the removed access documents are not be purged.

### Steps

1. Load `posts` dataset into a database.
2. Start a replicator: 
   * collections : 
      * `_default_.posts`
   * endpoint: `/posts`
   * type: pull
   * continuos: false
   * autoPurge: true
3. Wait until the replicator is stopped.
4. Check that the docs that the user has access to are all pulled.
5. Update docs on SG:
   * Update `post_1` by removing the user's `username` and `public` from the `channels` property.
   * Update `post_2` by removing the user's `username` and `public` from the `channels` property.
6. Start a replicator: 
   * collections : 
      * `_default_.posts`
      * pullFilter:
         name: documentIDs
         params : { "documentIDs": ["post_1"] }
   * endpoint: `/posts`
   * type: pull
   * continuos: false
   * autoPurge: true
7. Wait until the replicator is stopped.
8. Check local documents:
   * `post_1` was purged.
   * `post_2` still exists.
9. Check document replications:
   * `post_1` has access-removed flag set with no error.
   * `post_2` has access-removed flag set with WebSocket/403 error.
