# TTL (Time To Live) Tests

## test_document_expiry_unix_timestamp

Test document expiration using Unix timestamp format.

1. Create bucket and default collection
2. Configure Sync Gateway database endpoint
3. Create user 'vipul' with access to NBC, ABC
4. Create documents with different expiry times
5. Verify both documents exist initially
6. Wait for exp_3 document to expire
7. Verify exp_3 document is expired (not accessible)
8. Verify exp_years document is still accessible

## test_string_expiry_as_iso_8601_date

Test document expiration using ISO-8601 date format.

1. Create bucket and default collection
2. Configure Sync Gateway database endpoint
3. Create user 'vipul' with access to NBC, ABC
4. Create documents with ISO-8601 expiry dates
5. Verify both documents exist initially
6. Wait for exp_3 document to expire
7. Verify exp_3 document is expired (not accessible)
8. Verify exp_years document is still accessible
