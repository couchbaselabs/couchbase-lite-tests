# Access Control Replication Tests (Edge Server)

Couchbase Lite replication with basic auth against Edge Server with `enable_user_access_control` on. Pull needs read
access per collection, and push needs read and write per collection.

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

Every test starts the same way: start Edge Server, seed `<prefix>_es_hotels` in `travel.travel.hotels` and
`<prefix>_es_airlines` in `travel.travel.airlines`, and reset local database `db1` with collections
`travel.hotels` and `travel.airlines`. Replicators are one-shot, on `travel.hotels` unless stated otherwise.
The config allows CORS from `http://localhost:5173`, so the tests also run on the CBL-JS test server.

## test_read_write_user_syncs_both_ways

### Steps

1. Start Edge Server with access control on, seed one doc per collection, and reset `db1`.
2. Create 3 local docs, and push and pull as `rw` (`travel.*`: read, write).
3. Verify the replicator stopped without error, the docs were pushed, and the seed was pulled.

## test_read_only_user_can_pull

### Steps

1. Start Edge Server with access control on, seed one doc per collection, and reset `db1`.
2. Pull as `ro` (`travel.*`: read).
3. Verify the pull stopped without error and the seed was pulled.

## test_read_only_user_cannot_push

### Description

A read-only user's connection is pull-only, so Edge Server refuses the whole replicator as soon as it tries to push
(403, "Attempting to push to a pull-only replicator"), rather than pulling and dropping the push.

### Steps

1. Start Edge Server with access control on, seed one doc per collection, and reset `db1`.
2. Create 3 local docs, and push and pull as `ro`.
3. Verify the replicator is refused as pull-only (403), and none of the docs reached Edge Server.

## test_admin_syncs_every_collection

### Steps

1. Start Edge Server with access control on, seed one doc per collection, and reset `db1`.
2. Create a local doc in each collection, and push and pull both as `admin_user`.
3. Verify the replicator stopped without error and both collections synced both ways.

## test_collection_grants_apply_to_sync

### Description

`mixed` can read both collections but write only `travel.hotels`. The pull and each push run as separate
replicators, so a refused push to one collection cannot stop the allowed pull or push.

### Steps

1. Start Edge Server with access control on, seed one doc per collection, and reset `db1`.
2. Pull both collections as `mixed`, and verify both seeded docs arrive.
3. Push a doc to `travel.hotels` as `mixed`, and verify it lands.
4. Push a doc to `travel.airlines` as `mixed`, and verify it does not land.

## test_user_without_read_access_is_refused

### Description

Parametrized over `none` (`{}`), `wo` (write only, so it can read nothing) and `names_rw` (a grant on another
database).

### Steps

1. Start Edge Server with access control on, seed one doc per collection, and reset `db1`.
2. Create a local doc, and push and pull `travel` as the user.
3. Verify the replicator is refused and nothing crossed in either direction.