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

## test_sgcollect_redacted_files_and_contents

Test SGCollect REST API for redacted files and log file contents (Combined test).

This comprehensive test uses the `/_sgcollect_info` REST API to trigger SGCollect with partial redaction, then verifies:
1. All expected log files are present in the zip
2. Sensitive data is marked with `<ud>` tags in redacted files  
3. sync_gateway.log contains correct system information (hostname)

**Prerequisites**: Sync Gateway bootstrap.json must be configured with `redaction_level: "partial"` in the logging section.

1. Create bucket and default collection
2. Configure Sync Gateway
3. Create user 'vipul' with access to ['logging']
4. Create 10 docs via Sync Gateway
5. Start SGCollect via REST API and wait for it to complete
6. Download and extract SGCollect redacted zip
7. Verify redacted zip marks sensitive data with <ud> tags
8. Verify content of sync_gateway.log
