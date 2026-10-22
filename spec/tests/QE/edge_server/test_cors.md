# CORS Tests (Edge Server)

## test_cbl_js_replication_needs_cors

### Description

Test that a CBL-JS replicator in a browser can pull from Edge Server only when Edge Server's CORS configuration
allows the browser's origin.

| Case | `cors.origin` | Expected                                                                                                    |
|---|---|-------------------------------------------------------------------------------------------------------------|
| `test_server_origin` | `["http://localhost:5173"]`, the test server's origin | The pull succeeds                                                                                           |
| `wildcard_origin` | `["*"]`, any origin | The pull fails: authentication requires explicit origins                                                                                            |
| `other_origin_only` | `["https://app.example.com"]`, an origin that is not the test server's | The pull fails: CORS is configured, but not for this origin, which is the most likely configuration mistake |
| `cors_off` | no `cors` block | The pull fails: Edge Server sends no CORS headers, so the browser blocks every response                     |

Every case uses the same `headers` (`Authorization`, `Content-Type`) and `max_age` (600), so the origin list is the
only difference. The replicator authenticates with basic auth, so the `Authorization` header must be allowed. It is
limited to the one seeded document, so the pull is quick and only the test's own document is checked.

When CORS does not allow the origin, the browser blocks Edge Server's responses before CBL-JS sees them, so the
replicator stops with an error and pulls nothing; the test does not depend on the error's code or wording.

### Steps

1. Start Edge Server with the case's CORS origins, and seed a doc in `travel.hotels`.
2. Pull the seed doc from the browser as the admin.
3. Verify the pull succeeds only when CORS allows the test server's origin.