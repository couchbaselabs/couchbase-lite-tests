# Public API Schema Tests (Edge Server)

## test_public_api_conforms_to_spec

### Description

Runs schemathesis against a subset of the Edge Server public REST API. Schemathesis generates requests from the
OpenAPI spec that the Couchbase docs site publishes. It checks the status codes, content types and response bodies
against that spec.

The published spec describes only the current Edge Server release. The test skips when the major and minor version
of the server differ from the `info.version` of the spec.

Edge Server runs `config/test_public_api_schema.json`, which seeds the `names` dataset, declares the provisioned
admin user and defines the `female_ids` named query, which has no parameters. The config also creates two empty
collections, `schema_coll` in the default scope and `schema_coll` in `schema_scope`. Schemathesis signs in as the admin user, because
`_active_tasks` needs the admin role. The `{db}` and `{keyspace}` path parameters always name the `names` database,
and `{name}` names the query, so that requests reach real data instead of returning 404. A fixed seed and
deterministic generation make every run send the same requests.

The test runs once for each keyspace form: `names` (the default collection), `names.schema_coll` and
`names.schema_scope.schema_coll`. For a named collection, the test first copies the pinned documents into it, with
their dataset revisions, so that the same pins work there.

Positive mode sends only requests that the spec says are valid, and checks the responses.
Negative mode sends only requests that the spec says are invalid, for example a wrong type or a missing required
property, and checks that each one gets a 4xx, not a 5xx. Negative mode runs only against `names`, because the
keyspace is pinned, so it does not change between keyspaces. Each request times out after 10 seconds, so a request
that Edge Server never answers fails the test.

The operations in scope are:

- Collections: `PUT /{keyspace}`. Edge Server 1.1.1 never allows it to create a database or collection, so every
  request is a 403. The test checks that Edge Server refuses each request cleanly.
- Reads: `GET /`, `GET /_all_dbs`, `GET /_active_tasks`, `GET /{keyspace}`, `GET` and `POST /{keyspace}/_all_docs`,
  and `GET` and `HEAD /{keyspace}/{docid}`, with `{docid}` fixed to `name_1`.
- Writes: `PUT` and `DELETE /{keyspace}/{docid}` and `POST /{keyspace}/_bulk_docs`, with generated document IDs.
- Keys: `GET`, `PUT` and `DELETE /{keyspace}/{docid}/{key}`. Each uses its own `names` document (`name_1`,
  `name_2` and `name_3`) and an existing key. The writes use the dataset revision, so only the first write
  succeeds, and later ones get a 409.
- Queries and changes: `POST /{keyspace}/_query`, `GET` and `POST /{keyspace}/_query/{name}`, and
  `GET /{keyspace}/_changes` with `feed=normal`, so that no request waits for new changes.
- Sessions and replications: `POST /{db}/_session`, `GET /_replicate`, and `GET` and `DELETE /_replicate/{taskid}`.
  The test starts two continuous replications to a port on the Edge Server host that nothing listens on, so that
  they stay listed and send nothing off the host. The `GET` uses one task and the `DELETE` uses the other.
  `POST /_replicate` is not covered, because generated targets could be any host.

The spec has no links, so the stateful phase is off.

`tests/QE/edge_server/schemathesis.toml` lists the known mismatches for each operation. It turns off single checks
where the spec is wrong or where Edge Server has a known bug. Any other failure fails the test.

### Steps

1. Start Edge Server with the names dataset, the admin user and a named query.
2. Fetch the public API spec, and skip if it is for another Edge Server release.
3. For a named collection, copy the pinned documents into it, with their dataset revisions.
4. Start two continuous replications to an unreachable target, one to read and one to stop.
5. Run schemathesis in positive or negative mode against the public API operations in the keyspace.
6. Check that schemathesis found no failures.
