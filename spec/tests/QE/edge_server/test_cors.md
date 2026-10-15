# CORS Tests (Edge Server)

## test_preflight_from_allowed_origin

### Steps

1. Start Edge Server with CORS allowing two origins.
2. Send a preflight OPTIONS /travel/_all_docs from the allowed origin.
3. Verify the preflight allows the origin, the method and the Authorization header, with the max age.

## test_preflight_from_disallowed_origin

### Steps

1. Start Edge Server with CORS allowing two origins.
2. Send a preflight OPTIONS /travel/_all_docs from an origin that is not allowed.
3. Verify the response does not allow the origin.

## test_request_from_allowed_origin

### Steps

1. Start Edge Server with CORS allowing two origins.
2. Send GET /travel/ as the admin from the allowed origin.
3. Verify the request succeeds and the response allows the origin.

## test_request_from_disallowed_origin

### Steps

1. Start Edge Server with CORS allowing two origins.
2. Send GET /travel/ as the admin from an origin that is not allowed.
3. Verify the response does not allow the origin.

## test_cors_does_not_bypass_authentication

### Steps

1. Start Edge Server with CORS allowing two origins.
2. Send GET /travel/ from the allowed origin with no credentials.
3. Verify the request is refused with 401, and the refusal allows the origin so a browser can read it.

## test_wildcard_origin_allows_any_origin

### Steps

1. Start Edge Server with CORS allowing any origin.
2. Send a preflight OPTIONS /travel/_all_docs from an arbitrary origin.
3. Verify the preflight allows the origin.

## test_cors_is_off_without_config

### Steps

1. Start Edge Server with no `cors` block.
2. Send a preflight and a GET /travel/ as the admin from an origin.
3. Verify neither response allows the origin.

## test_cbl_js_replication_needs_cors

### Steps

1. Start Edge Server with or without CORS for the test server's origin, and seed a doc.
2. Pull the seed doc from the browser as the admin.
3. Verify the pull succeeds with CORS, and fails with nothing pulled without it.