# TTL (Time To Live) Tests

## test_document_expiry_unix_timestamp

Test document expiration using Unix timestamp format.

1. Configure Sync Gateway database endpoint
2. Create user 'vipul' with access to NBC, ABC
3. Create documents with different expiry times
4. Verify both documents exist initially
5. Wait for exp_3 document to expire
6. Verify exp_3 document is expired (not accessible)
7. Verify exp_years document is still accessible

## test_string_expiry_as_iso_8601_date

Test document expiration using ISO-8601 date format.

1. Configure Sync Gateway database endpoint
2. Create user 'vipul' with access to NBC, ABC
3. Create documents with ISO-8601 expiry dates
4. Verify both documents exist initially
5. Wait for exp_3 document to expire
6. Verify exp_3 document is expired (not accessible)
7. Verify exp_years document is still accessible
