# Replication Functional Tests

This document describes the functional tests for replication behavior in Couchbase Lite with tests including multiple channels/users/roles and interacting with Sync Gateway.

## test_roles_replication

Test replication behavior with role-based access control.

1. Reset SG and load `posts` dataset.
2. Reset local database and load `posts` dataset.
3. Create test user 'testuser' with no initial roles.
4. Create role1 with access to group1 channel.
5. Create role2 with access to group2 channel.
6. Assign only role1 to testuser initially.
7. Create initial documents in both channels on SGW:
   * Documents in group1 channel (should be accessible)
   * Documents in group2 channel (should NOT be accessible initially)
8. Start initial pull replication:
   * endpoint: `/posts`
   * collections: `_default.posts`
   * type: pull
   * continuous: false
   * credentials: testuser/testpass
9. Wait until the initial replicator stops.
10. Verify docs got replicated from only group1 channel:
    * Should have: post_1, post_2, post_3 (from dataset), initial_group1_doc1, initial_group1_doc2
    * Should NOT have: post_4, post_5 (group2 from dataset), initial_group2_doc1, initial_group2_doc2
11. Add role2 to testuser to grant access to group2 channel.
12. Add new documents to SGW in both channels.
13. Start the replicator again.
14. Wait until the second replicator stops.
15. Verify all docs got replicated from both channels:
    * Should now have ALL documents from both group1 and group2
    * From dataset: post_1, post_2, post_3, post_4, post_5
    * Initial docs: initial_group1_doc1, initial_group1_doc2, initial_group2_doc1, initial_group2_doc2
    * New docs: new_group1_doc1, new_group1_doc2, new_group2_doc1, new_group2_doc2
16. Verify specific documents from group2 that were previously inaccessible.

## test_CBL_SG_replication_with_rev_messages

Test replication behavior with revision messages and document purging.

Parametrized over `channel`: `*` (wildcard) and `ChannelA` (an explicit channel name),
used as the `channels` value on every document created in this test. Both
variants are otherwise identical — user1 keeps its default dataset-configured
`*` access in both cases. When `channel` is `*` and Sync Gateway is configured
to use views (i.e. `enable_shared_bucket_access` is disabled), the "Verify
replication completed successfully" step is skipped: checking the progress on
documents explicitly assigned the `*` channel will show `completed: false`
instead of `true` when running with views. There are no other non progress
side effects. See CBG-5573 and CBL-8624.

1. Reset SG and load `short_expiry` dataset.
2. Reset local database.
3. Create initial document in CBL.
4. Start continuous push replication to sync doc_1 to SGW:
   * endpoint: `/short_expiry`
   * collections: `_default._default`
   * type: push
   * continuous: true
   * credentials: user1/pass
5. Wait for initial push replication to complete.
6. Verify doc_1 exists in SGW.
7. Purge doc_1 from SGW.
8. Verify doc_1 is purged from SGW.
9. Create 2 new documents in CBL to flush doc_1's revision from SGW's rev_cache:
   * rev_cache size = 1, so creating 2 docs will definitely flush doc_1's revision
10. Verify documents were created in local database.
11. Wait for new documents to be pushed to SGW.
12. Verify documents exist in SGW.
13. Reset the database.
14. Verify the recreated database is empty.
15. Start pull replication from SGW to recreated database:
    * endpoint: `/short_expiry`
    * collections: `_default._default`
    * type: pull
    * continuous: false
    * credentials: user1/pass
16. Wait for pull replication to finish.
17. Verify replication completed successfully (skipped for `channel` `*` on views — see above).
18. Verify all docs from SGW replicated successfully:
    * Should have: doc1 (from dataset), doc_2, doc_3 (created docs)
    * Should NOT have: doc_1 (purged document)
19. Verify specific document contents.

## test_replication_behavior_with_channelRole_modification

Test replication behavior when modifying channel access through roles.

1. Reset SG and load `posts` dataset.
2. Reset local database and load `posts` dataset.
3. Create test user 'testuser' with no initial access.
4. Create role 'testrole' with access to group1 channel.
5. Assign testrole to testuser.
6. Create initial documents in group1 channel on SGW.
7. Start continuous pull replication from SGW:
   * endpoint: `/posts`
   * collections: `_default.posts`
   * type: pull
   * continuous: true
   * credentials: testuser/testpass
8. Wait for initial pull replication to complete.
9. Verify initial docs got replicated to CBL:
   * Should have: post_1, post_2, post_3 (from dataset), initial_doc1, initial_doc2 (created)
   * Should NOT have: post_4, post_5 (group2 from dataset)
10. Change testrole's channel access from group1 to group2.
11. Add new documents to SGW in group1 channel (should NOT be accessible).
12. Add new documents to SGW in group2 channel (should be accessible).
13. Wait for replicator to detect new group2 document.
14. Wait for replicator to finish pulling.
15. Verify CBL did NOT get new docs from group1 channel after role change:
    * Should have: post_1, post_2, post_3, post_4, post_5 (from dataset) + new_group2_doc1 (new doc in group2)
    * Should NOT have: initial_doc1, initial_doc2 (group1 no longer accessible), new_group1_doc1, new_group1_doc2 (group1 no longer accessible)
16. Verify specific document contents.

## test_default_conflict_withConflicts_withChannels

Test default conflict resolution with channel-based access control. Sync Gateway 3.x runs conflict-free (stored conflicts are not supported), so the conflict is produced on the client at pull time through divergent CBL and SGW edits from the same base revision.

1. Reset SG and load `posts` dataset.
2. Create two users with access to different channels:
   * user1 with access to channel1
   * user2 with access to channel2
3. Create initial documents in both channels.
4. Create a CBL database with the `posts` collection (load the `posts` dataset so `_default.posts` exists).
5. Start a one-shot pull replicator to seed the shared documents into CBL:
   * endpoint: `/posts`
   * collections: `_default.posts`
   * type: pull
   * continuous: false
   * credentials: user1/pass1
6. Verify the shared documents replicated into CBL.
7. Create a conflict for each shared document via divergent edits from the same base revision:
   * Edit the document locally in CBL (unsynced).
   * Edit the same document on Sync Gateway twice, so the server revision is a higher generation than the local edit.
8. Pull again with the default conflict resolver (none specified); CBL resolves the conflicts without a replication error.
9. Verify each conflict resolved to a single revision holding one of the conflicting edits.
10. Update the resolved documents in CBL (final, deterministic state):
    * shared_doc1 updated by user1, version 3
    * shared_doc2 updated by user2, version 3
11. Push the resolved documents back to Sync Gateway (push-and-pull, one-shot, user1/pass1).
12. Verify Sync Gateway converged on the CBL updates:
    * Titles reflect the CBL updates
    * Version numbers are 3
