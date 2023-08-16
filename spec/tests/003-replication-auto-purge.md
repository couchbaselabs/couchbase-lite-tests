# Test Cases

## test_remove_docs_from_channel_with_auto_purge_enabled

### Description

Test that the replicator will purged the docs that the user lost the access to by removing the docs from all user's channels.

### Steps

1. Reset SG and load `posts` dataset.
2. Reset local database, and load `posts` dataset.
3. Start a replicator: 
    * collections : 
      * `_default_.posts`
    * endpoint: `/posts`
    * type: pull
    * continuos: false
    * autoPurge: true
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that the docs that the user has access to are all pulled.
6. Update docs on SG:
   * Update `post_1` with channels = [] (ACCESS-REMOVED)
   * Update `post_2` with channels = ["group1"]
   * Update `post_3` with channels = ["group2"]
   * Delete `post_4`
7. Start the replicator with the same config as the step 3.
8. Wait until the replicator is stopped.
9. Check local documents:
   * `post_1` was purged.
   * `post_2` and `post_3` were updated with the new channels.
   * `post_4` was deleted.
10. Check document replications (NEED REST API):
   * `post_1` has access-removed flag set.
   * `post_2` and `post_3` have no flags set.
   * `post_4` has deleted flag set.

## test_revoke_access_with_auto_purge_enabled

### Description

Test that the replicator will purged the docs that the user lost the access to by revoking the access to all of the user's channels that the docs are in.

1. Reset SG and load `posts` dataset.
2. Reset local database, and load `posts` dataset.
3. Start a replicator: 
    * collections : 
      * `_default_.posts`
    * endpoint: `/posts`
    * type: pull
    * continuos: false
    * autoPurge: true
    * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that the docs that the user has access to are all pulled.
6. Update user access to channels on SG:
    * Remove access to `group2` channel.
7. Start the replicator with the same config as the step 3.
8. Wait until the replicator is stopped.
9. Check local documents:
   * `post_4` and `post_5` were purged.
10. Check document replications:
   * `post_4` and `post_5` have access-removed flag set.
11. Update user access to channels on SG:
    * Add user access to `group2` channel back again.
12. Start the replicator with the same config as the step 3.
13. Wait until the replicator is stopped.
14. Check local documents:
    * `post_4` and `post_5` are back.
15. Check document replications:
    * `post_4` and `post_5` have events with no flags set.
   
## test_remove_docs_from_channel_with_auto_purge_diabled

### Description

Test that when auto-purge is disabled, the replicator will not purge the docs that the user lost the access to from removing the docs from all user's channels.

**Notes**
* The document replication events for the removed-access docs should have the access-removed flag set.

### Steps

1. Reset SG and load `posts` dataset.
2. Reset local database, and load `posts` dataset.
3. Start a replicator: 
   * collections : 
      * `_default_.posts`
   * endpoint: `/posts`
   * type: pull
   * continuos: false
   * autoPurge: false
   * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that the docs that the user has access to are all pulled.
6. Update docs on SG:
   * Update `post_1` with channels = [] (ACCESS-REMOVED)
   * Update `post_2` with channels = ["group1"]
   * Update `post_3` with channels = ["group2"]
7. Start the replicator with the same config as the step 3.
8. Wait until the replicator is stopped.
9. Check local documents:
   * `post_1`, `post_2` and `post_3` are updated with the new channels.
10. Check document replications (NEED REST API):
   * `post_1` has access-removed flag set.
   * `post_2` and `post_3` have no flags set.

## test_revoke_access_with_auto_purge_disabled

### Description

Test that when auto-purge is disabled, the replicator will not purge the docs that the user lost the access to by revoking the access to all of the user's channels that the docs are in.

**Notes**
* The document replication events for the removed-access docs should have the access-removed flag set.
* For the removed-access docs from the access revoked (no changes in their properties), if there is a pull filter set, the pull filter will not be called for those removed-access docs as auto-purge is disabled. 

1. Reset SG and load `posts` dataset.
2. Reset local database, and load `posts` dataset.
3. Start a replicator: 
   * collections : 
      * `_default_.posts`
   * endpoint: `/posts`
   * type: pull
   * continuos: false
   * autoPurge: false
   * credentials: user1/pass
3. Wait until the replicator is stopped.
4. Check that the docs that the user has access to are all pulled.
5. Update user access to channels on SG:
   * Remove access to `group2` channel.
6. Start the replicator with the same config as the step 3.
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
   * credentials: user1/pass
8. Wait until the replicator is stopped.
9. Check local documents:
   * `post_4` and `post_5` are not purged.
10. Check document replications (NEED REST API):
    * `post_4` and `post_5` have access-removed flag set but no errors (When a change was reject by the filter, the document replication will have WebSocket/403 error)

## test_filter_removed_access_documents

### Description

Test that when the removed access documents are filtered, the removed access documents are not be purged.

### Steps

1. Reset SG and load `posts` dataset.
2. Reset local database, and load `posts` dataset.
3. Start a replicator: 
   * collections : 
      * `_default_.posts`
   * endpoint: `/posts`
   * type: pull
   * continuos: false
   * autoPurge: true
   * credentials: user1/pass
4. Wait until the replicator is stopped.
5. Check that the docs that the user has access to are all pulled.
6. Update docs on SG:
   * Update `post_1` with channels = [] (ACCESS-REMOVED)
   * Update `post_2` with channels = [] (ACCESS-REMOVED)
7. Start a replicator: 
   * collections : 
      * `_default_.posts`
      * pullFilter:
         name: documentIDs
         params : { "documentIDs": ["post_1"] }
   * endpoint: `/posts`
   * type: pull
   * continuos: false
   * autoPurge: true
   * credentials: user1/pass
8. Wait until the replicator is stopped.
9. Check local documents:
   * `post_1` was purged.
   * `post_2` still exists.
10. Check document replications (NEED REST API):
   * `post_1` has access-removed flag set with no error.
   * `post_2` has access-removed flag set with WebSocket/403 error.
