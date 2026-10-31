# Public API Authorization Tests (Edge Server)

## test_public_api_authorization

### Description

Checks which users can use each Edge Server public REST API operation. The Edge Server spec declares no
security schemes, so this test holds the expected access in a table, and does not use schemathesis.

Edge Server runs `config/test_public_api_authorization.json`. It serves the `names` dataset with
`enable_user_access_control` on, and reads its users from a file that the test writes first:

| User | Role or access |
|------|----------------|
| `qe_admin` | `admin` role |
| `replicator` | `replicate` role |
| `writer` | `read` and `write` on `names` |
| `reader` | `read` on `names` |
| `write_only` | `write` on `names` |
| `no_access` | an empty access entry |

The test also runs as an anonymous user (anonymous users are on), and as `reader` with a wrong password.

The test runs once per user. It sends one valid request per operation, and records whether the request
succeeds or which status refuses it. The expected access is:

- `GET /` and `GET /_all_dbs`: everyone with valid credentials, and anonymous users.
- `GET /_active_tasks`: `qe_admin` only.
- `GET /_replicate`, and `GET` and `DELETE /_replicate/{taskid}`: `qe_admin` and `replicator`.
- Reads of the database, its documents, changes and queries: `qe_admin`, `replicator`, `writer` and `reader`.
- `POST /{db}/_session`: every user with read or write access.
- Documents with generated IDs (`POST /{keyspace}`, and `_bulk_docs` rows with no `_id`): every user with
  write access, which includes `write_only`.
- Every other write: `qe_admin`, `replicator` and `writer`.

Every other user gets a 403. An anonymous user gets a 401 for the operations that need a role, and for
`_session`. A wrong password gets a 401 for every operation.

Each write uses its own document, with the revision that the admin reads first. So an allowed write succeeds,
and does not depend on the order of the requests. The replication operations use a continuous
replication to a port on the Edge Server host. Nothing listens on that port.

`KNOWN_BUGS` in the test lists the requests that Edge Server allows although it must not. A listed request
must still give the listed status. If Edge Server fixes the bug, the test fails, and the entry must be removed.

### Steps

1. Write the users file, and start Edge Server with access control on the names dataset.
2. As the admin, read the revisions of the documents to change, and start a replication.
3. Send one valid request per operation as the user, and record each status.
4. Check each status against the expected access and the known bugs.
