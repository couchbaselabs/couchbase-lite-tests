# Versioned request/response API between Client and Test Servers

The Client drives Test Servers written in five languages, and a single Client
must work against multiple Couchbase Lite releases at once (the matrix spans
older and newer CBL builds). To keep these decoupled, the Client↔Test Server
protocol is explicitly versioned: every versioned request carries a
`CBLTest-API-Version` header (the initial unversioned `GET /` handshake is the
one exception), and the Client implements each version side-by-side under
`client/src/cbltest/v1/` and `v2/`, registered via `@register_request` /
`@register_body`. `version.py::available_api_version()` is the source of truth.

This lets a Test Server and the Client negotiate a common version at startup, so
platforms can adopt a new API version on their own schedule without breaking the
existing test matrix.

## Consequences

- Adding API surface means picking a version and registering request/response
  bodies under the matching `vN/` package — not editing a shared monolith.
- The OpenAPI spec in `spec/api/api.yaml` is the cross-language contract all
  Test Server implementations target.
