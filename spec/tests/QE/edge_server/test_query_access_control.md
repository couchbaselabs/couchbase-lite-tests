# Query Access Control Tests (Edge Server)

Named query access control with `enable_user_access_control` on. A named query without an `allow` property is a
**database-level** query: a user with read access to at least one collection in the database can run it. A query
with `allow.collections` is **collection-restricted**: only a user with read access to at least one listed collection
can run it.

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

The named queries:

| Database | Query | Statement | `allow.collections` |
|---|---|---|---|
| `travel` | `airline_ids` | `SELECT meta().id FROM travel.airlines LIMIT 5` | none (database-level) |
| `travel` | `hotel_ids` | `SELECT meta().id FROM travel.hotels LIMIT 5` | `travel.hotels`, `travel.landmarks` |
| `names` | `name_ids` | `SELECT meta().id FROM _default LIMIT 5` | none (database-level) |

A named query is called as `/{keyspace}/_query/{name}`, and Edge Server first checks that the user can access the
keyspace in the URL. `/travel/_query/...` targets `travel._default._default`, so each user's queries are called
through a keyspace that user can read. A refused query answers 403.

## test_admin_runs_every_named_query

### Steps

1. Start Edge Server with access control on and the named queries.
2. Verify the admin can run `airline_ids`, `hotel_ids` and `name_ids`, and each returns rows.

## test_database_level_query_needs_read_on_any_collection

### Description

A database-level query is open to a user who can read any collection in the database, even one the query does not
read.

### Steps

1. Start Edge Server with access control on and the named queries.
2. Verify `airline_rw` can run `airline_ids`, and it returns airline IDs.
3. Verify `landmark_reader` can run `airline_ids`: it can read a collection in `travel`.
4. Verify `wo` (`travel.*`: write) cannot run `airline_ids`: it can read nothing.

## test_collection_restricted_query_needs_read_on_a_listed_collection

### Description

The docs' own example: `landmark_reader` is the docs' `foo`, and `airline_rw` is `bar`.

### Steps

1. Start Edge Server with access control on and the named queries.
2. Verify `mixed` (reads `travel.hotels`) can run `hotel_ids`, and it returns hotel IDs.
3. Verify `landmark_reader` can run `hotel_ids`: `travel.landmarks` is in its allow list.
4. Verify `airline_rw` cannot run `hotel_ids`: it reads no listed collection.

## test_no_access_user_runs_no_query

### Steps

1. Start Edge Server with access control on and the named queries.
2. Verify `none` ({}) can run neither `travel` query.

## test_query_access_is_per_database

### Steps

1. Start Edge Server with access control on and the named queries.
2. Verify `names_rw` can run `name_ids` on `names`.
3. Verify `rw` (`travel.*`) cannot run `name_ids` on `names`.

## test_query_is_checked_against_the_url_keyspace

### Description

The same query, by the same user, succeeds or fails depending only on the keyspace in the URL.

### Steps

1. Start Edge Server with access control on and the named queries.
2. Verify `landmark_reader` can run `hotel_ids` through `travel.travel.landmarks`.
3. Verify `landmark_reader` is refused `hotel_ids` through `travel`, its default collection.

## test_adhoc_query_cannot_read_an_unpermitted_collection

### Description

The docs say access control policies apply to named queries only. This test checks that an ad hoc query, called
through a keyspace the user can read, still cannot read a collection the user has no access to. If ad hoc queries
are deliberately outside access control, this test documents the exposure.

### Steps

1. Start Edge Server with access control on and ad hoc queries enabled on `travel`.
2. Verify `airline_rw` can run an ad hoc query on `travel.airlines`.
3. Verify `airline_rw` cannot read `travel.hotels` with an ad hoc query.