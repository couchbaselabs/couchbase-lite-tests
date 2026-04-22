# Large Document Workloads

## test_doc_body_size_boundary

Test SGW enforcement of the 20 MB document body size limit via SGW admin API. Documents at 19.9 MB and 20.1 MB are created directly through the admin API, verifying acceptance/rejection at the boundary and that SGW remains functional afterwards.

1. Create bucket on Couchbase Server.
2. Configure Sync Gateway database endpoint.
3. Create a 19.9 MB document via SGW admin API — expect acceptance.
4. Verify the 19.9 MB document is retrievable from SGW with correct content.
5. Verify 19.9 MB doc appears in _all_docs listing on SGW.
6. Attempt to create a 20.1 MB document via SGW admin API — expect HTTP 413.
7. Verify the rejected 20.1 MB document does NOT exist in SGW.
8. Verify rejected doc does NOT appear in _all_docs listing.
9. Create a normal 1 KB document to confirm writes still work after rejection.
10. Verify SGW endpoints are responsive — _config, _changes, _all_docs, database status.
11. Verify previously accepted 19.9 MB doc is still accessible.
12. Verify CBS bucket — rejected doc must NOT exist.

## test_oversized_attachment_push

Test that SGW rejects a 50 MB blob attachment pushed via BLIP replication from CBL, while the local CBL database remains intact. Uses xl2.jpg (50 MB) from dataset/server/blobs/ — well beyond SGW's 20 MB attachment limit.

1. Create bucket on Couchbase Server.
2. Configure Sync Gateway database endpoint.
3. Create user 'blobuser' with channel access.
4. Reset local database with empty collection.
5. Create a document with a 50 MB blob attachment (xl2.jpg) in CBL.
6. Verify the document and blob exist locally in CBL.
7. Also create a small control document to verify partial replication works.
8. Push replicate to SGW — expect SGW to reject the 50 MB blob.
9. Verify SGW did NOT receive the oversized-blob document.
10. Verify the oversized doc is not retrievable from SGW.
11. Verify the small control document WAS successfully replicated.
12. Verify local CBL database integrity — blob doc still intact.
13. Verify local control doc also still intact.
14. Verify local database has exactly 2 documents.
15. Verify CBS bucket — control doc present, blob doc NOT present.
