# Session Tests (Edge Server)

## test_create_session_requires_one_time_true

### Description

Test that only `one_time=true` is accepted. Parametrized over `one_time` missing, `false`, empty, `0` and `random`.

### Steps

1. Start Edge Server on the session config with the test users.
2. Verify POST /travel/_session with the case's one_time is rejected with 400.

## test_create_session_rejects_bad_credentials

### Description

Test that minting a session needs valid credentials. Parametrized over a wrong password, an unknown user and no
credentials.

### Steps

1. Start Edge Server on the session config with the test users.
2. Verify POST /travel/_session?one_time=true with the case's credentials is rejected with 401.

## test_create_session_unknown_database

### Steps

1. Start Edge Server on the session config with the test users.
2. Verify POST /nosuchdb/_session?one_time=true as admin is rejected with 404.

## test_create_session_access_control

### Description

Test which users can mint a session for which database.

| Case | User | Database | Expected |
|---|---|---|----------|
| `read_write` | `rw` | `travel` | 200      |
| `read_only` | `ro` | `travel` | 200      |
| `one_readable_collection` | `coll` | `travel` | 200      |
| `own_database` | `other_db` | `names` | 200      |
| `write_only` | `wo` | `travel` | 200      |
| `no_access` | `none` | `travel` | 403      |
| `other_database` | `other_db` | `travel` | 403      |
| `unlisted_database` | `rw` | `names` | 403      |

### Steps

1. Start Edge Server on the session config with the test users.
2. Verify POST /{db}/_session?one_time=true as the user issues a session, or is rejected.