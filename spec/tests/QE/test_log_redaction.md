# Log Redaction Tests

## test_log_redaction_partial

Test that Sync Gateway properly redacts sensitive data in logs (NEGATIVE TEST).

This test verifies that NO document IDs or usernames appear in logs WITHOUT `<ud>...</ud>` tags when log redaction is enabled at the "partial" level.

**Prerequisites**: Sync Gateway bootstrap.json must be configured with `redaction_level: "partial"` in the logging section.

1. Create bucket and default collection
2. Configure Sync Gateway with log redaction enabled
3. Create user 'autotest' with access to channels
4. Create 10 docs via Sync Gateway with xattrs
5. Verify docs were created
6. Fetch and scan SG logs for redaction violations
