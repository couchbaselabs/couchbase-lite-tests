# Log Redaction Tests

## test_log_redaction_partial

Test that Sync Gateway properly redacts sensitive data in logs (NEGATIVE TEST).

This test verifies that NO document IDs or usernames appear in logs WITHOUT `<ud>...</ud>` tags when log redaction is enabled at the "partial" level.

**Prerequisites**: Sync Gateway bootstrap.json must be configured with `redaction_level: "partial"` in the logging section.

1. Create bucket and default collection
2. Configure Sync Gateway with log redaction enabled
3. Create user 'vipul' with access to channels
4. Create 10 docs via Sync Gateway
5. Verify docs were created (public API)
6. Fetch and scan SG logs for redaction violations

## test_redacted_files_via_command_line

Test that SGCollect properly marks sensitive data with redaction tags.

This test verifies that when `redaction_level` is "partial", SGCollect creates a redacted zip file where sensitive data (usernames, doc IDs) is marked with `<ud>...</ud>` tags.

**Prerequisites**: Sync Gateway bootstrap.json must be configured with `redaction_level: "partial"` in the logging section.

1. Create bucket and default collection
2. Configure Sync Gateway with log redaction enabled
3. Create user 'vipul' with access to ['log-redaction']
4. Create 10 docs via Sync Gateway
5. Verify docs were created via public API
6. Run SGCollect to generate diagnostic zip
7. Verify redacted zip marks sensitive data with <ud> tags

## test_sgcollect_via_rest_api

Test SGCollect REST API and verify all expected log files exist in generated zip.

This test uses the `/_sgcollect_info` REST API endpoint (instead of command line) to trigger collection, and verifies that all expected log files are present in the resulting zip and contain correct system information.

1. Create bucket and default collection
2. Configure Sync Gateway
3. Create user 'vipul' with access to ['logging']
4. Create 10 docs via Sync Gateway
5. Start SGCollect via REST API and wait for it to complete
6. Verify all expected log files exist in SGCollect zip
7. Verify content of sync_gateway.log
