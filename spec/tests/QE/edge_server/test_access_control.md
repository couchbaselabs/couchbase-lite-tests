# Access Control Tests (Edge Server)

REST tests for fine-grained user access control with `enable_user_access_control` set at the server level.

Every test starts Edge Server on `config/test_access_control.json`: `enable_user_access_control: true`, anonymous
users disabled, and the provisioned `travel` and `names` datasets. The config reads its own users file,
`/home/ec2-user/user/access_control_users.json`; each test copies `config/test_access_control_users.json` there
before starting, so the provisioned `users.json` never gains an access block. Every user's password is `password`.
Every test skips on Edge Server older than 1.1.0.

| User | Roles | Access block |
|---|---|---|
| `admin_user` | `admin` | none |
| `admin_with_access` | `admin` | `names`: read |
| `replicator` | `replicate` | `{}` |
| `rw` | | `travel.*`: read, write |
| `ro` | | `travel.*`: read |
| `wo` | | `travel.*`: write |
| `none` | | `{}` |
| `mixed` | | `travel.travel.hotels`: read, write; `travel.travel.airlines`: read |
| `scope_reader` | | `travel.travel.*`: read |
| `default_reader` | | `travel`: read |
| `names_rw` | | `names.*`: read, write |
| `landmark_reader` | | `travel.travel.landmarks`: read |
| `airline_rw` | | `travel.travel.airlines`: read, write |

Over REST, a **read** is `_all_docs` and a **write** is a `PUT` with an ID. A 403 is a denial, and any other failure
fails the test.

## test_access_blocks_require_the_flag

### Description

Test that users with access blocks are refused when access control is off, rather than silently given full access.

### Steps

1. Start Edge Server with access control off and users that have access blocks.
2. Verify startup fails, saying access control must be enabled.

## test_no_access_user_is_denied_everywhere

### Description

Test that a user with an empty access block can reach nothing, and is shown no databases.

### Steps

1. Start Edge Server with access control on.
2. Verify `none` ({}) can neither read nor write any keyspace.
3. Verify /_all_dbs lists no databases for `none`.

## test_admin_has_full_access

### Description

Test that the admin role has full access to every keyspace and to the administrative endpoints.

### Steps

1. Start Edge Server with access control on.
2. Verify the admin can read and write every keyspace.
3. Verify /_all_dbs lists both databases for the admin.
4. Verify the admin can call /_active_tasks and /_replicate.

## test_admin_access_block_is_ignored

### Description

Test that an access block on an admin user does not restrict it.

### Steps

1. Start Edge Server with access control on.
2. Verify `admin_with_access` (admin role, `names`: read) can read and write `travel`.

## test_admin_endpoints_need_the_replicate_or_admin_role

### Description

Test that `/_active_tasks` and `/_replicate` need the `replicate` or `admin` role, independently of data access.

### Steps

1. Start Edge Server with access control on.
2. Verify `replicator` (replicate role, {}) can call /_active_tasks and /_replicate.
3. Verify `replicator` cannot read or write `travel`.
4. Verify `rw` (full data access, no role) cannot call /_active_tasks or /_replicate.

## test_keyspace_patterns

### Description

Test each keyspace pattern form in the docs: `database.*`, `database.scope.*`, `database` (the default collection
only) and `database.scope.collection`.

### Steps

1. Start Edge Server with access control on.
2. Verify `travel.*` covers the default collection and every scope.
3. Verify `travel.travel.*` covers the `travel` scope but not the default collection.
4. Verify `travel` covers only the default collection.
5. Verify `travel.travel.hotels` covers only that collection.
6. Verify a grant on `names` gives nothing on `travel`.

## test_missing_keyspace_is_403

### Description

Test that a keyspace that does not exist answers 403, like one the user may not access, so that users cannot discover
which keyspaces exist. `rw`'s `travel.*` grant covers the missing collection, so the 403 cannot come from the rule.

### Steps

1. Start Edge Server with access control on.
2. Verify `rw` (`travel.*`) gets 403 for a collection `travel` does not have.
3. Verify `rw` gets 403 for a database the server does not serve.