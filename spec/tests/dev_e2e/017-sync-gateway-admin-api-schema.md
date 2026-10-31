# Test Cases

## #1 test_admin_api_conforms_to_spec

### Description

Runs schemathesis against a subset of the Sync Gateway admin REST API. Schemathesis
generates requests from the OpenAPI spec that Sync Gateway publishes in its
repository. It checks the status codes, content types and response bodies against
that spec. It also runs stateful sequences, for example a user PUT followed by a GET.

The spec comes from the Sync Gateway release tag that matches the version of the
node under test. A development build has no tag, so it uses `main`.

The `{db}` and `{keyspace}` path parameters always name the test database, so
requests reach real data instead of returning 404. A fixed seed and deterministic
generation make every run send the same requests. The test sends only requests
that the spec says are valid.

`tests/dev_e2e/syncgateway/schemathesis.toml` lists the known mismatches for each
operation. It turns off single checks where the spec is wrong or where Sync Gateway
has a known bug. It also fixes some parameters, for example `feed=normal` on
`_changes`, so that no request hangs. Any other failure fails the test.

### Steps

1. Fetch the admin API spec for the Sync Gateway version under test.
2. Create a bucket-backed database that uses the default collection.
3. Run schemathesis against the admin API operations in scope.
4. Check that schemathesis found no failures.
