# Authentication Tests (Edge Server)

This document describes authentication and TLS tests for Couchbase Lite Edge Server.

## test_basic_auth

Test basic authentication with valid, invalid, and anonymous credentials.

1. Configure Edge Server with the `names` dataset using basic auth config.
2. Add a user with valid credentials and set the Edge Server auth to that user.
3. Fetch active tasks to verify valid auth succeeds.
4. Set invalid credentials and verify fetching active tasks fails.
5. Disable auth (anonymous) and verify fetching active tasks fails.

## test_valid_tls

Test TLS configuration for Edge Server.

1. Configure Edge Server with the `names` dataset using TLS config.
2. Fetch server version information and verify the call succeeds.
