# Per-Database User Access Control Tests (Edge Server)

These tests validate the per-database `enable_user_access_control` flag (CBL-8556, Edge Server
1.1.1). For database D the flag resolves to D's own key, else the root key, else `false`. Every
test skips on Edge Server older than 1.1.1.

Each test writes its users to `/home/ec2-user/user/per_db_access_users.json`, always including the
admin `qe_admin`, and then starts Edge Server. Console logging is on, so startup warnings can be read
from `/home/ec2-user/log/edge.log`. Over REST, a **read** is `_all_docs` and a **write** is a `PUT`
with an ID. A 403 is a denial, and any other failure fails the test.

Most tests use one of two configs. Each serves `enforced` (flag `true`), `exempt` (flag `false`)
and `inherits` (no flag), with anonymous access on:

| Config | Root flag | `inherits` resolves to |
|---|---|---|
| `test_per_db_access_control.json` | `true` | enforcing |
| `test_per_db_access_control_root_false.json` | `false` | open |

`test_per_db_access_control.json` also allows CORS from `http://localhost:5173`, so the CBL
JavaScript test server can replicate with it from a browser.

The shared users:

| User | Access block |
|---|---|
| `no_block` | none |
| `ruled` | `enforced: [read]`, `exempt: [read]` |
| `writer` | `enforced: [read, write]` |
| `write_only` | `enforced: [write]`, `exempt: [write]` |
| `star` | `*: [read]` |
| `restricted` | `{}` |

## test_unset_database_inherits_root_true

### Description

Test that a database with no flag inherits a root flag of `true`. This is how every shipped 1.1
config looks.

### Steps

1. Start Edge Server with root flag true and `inherits` setting no flag.
2. Verify `restricted` and anonymous are denied `inherits`.
3. Verify `star` (`*`: read) is read-only on `inherits`.
4. Verify `no_block` has full access to `inherits`.

## test_database_set_true_enforces_rules

### Description

Test that a database setting `true` enforces each kind of access block. A user with no access block
gets an implicit full grant, a user with rules gets exactly those rules, and a user with `{}` gets
nothing.

`write_only` covers the drop-box case. A write-only user can create documents only with
`POST /{keyspace}/`, which picks the ID. A `PUT` with an ID is refused (403, "Write-only access:
use POST with auto-generated ID"), since choosing an ID would let the user find out which documents
exist.

### Steps

1. Start Edge Server with root flag true and `enforced` setting true.
2. Verify the admin and `no_block` have full access to `enforced`.
3. Verify `ruled` is read-only and `writer` has full access to `enforced`.
4. Verify `write_only` can create with POST, but cannot read or PUT with an ID.
5. Verify `restricted` and anonymous are denied `enforced`.

## test_database_set_false_ignores_rules

### Description

Test that a database setting `false` overrides a root of `true`. Its rules are ignored, not
evaluated: a read-only user can write, a write-only user can read, and `{}` grants full access.

### Steps

1. Start Edge Server with root flag true and `exempt` setting false.
2. Verify every user, including anonymous, has full access to `exempt`.
3. Verify Edge Server warned that rules for `exempt` are ignored.

## test_root_false_enforces_only_databases_set_true

### Description

Test that with a root flag of `false`, only databases that set `true` are enforced. A database with
no flag is open, as in 1.0.

### Steps

1. Start Edge Server with root flag false, `enforced` true, `exempt` false and `inherits` unset.
2. Verify only `enforced` restricts `restricted`.
3. Verify `ruled` is read-only on `enforced`.

## test_access_does_not_leak_between_databases

### Description

Test that access to one database grants nothing on another. Full access to an exempt database, or a
rule for one enforcing database, must not become a way into the rest of the server.

### Steps

1. Start Edge Server with root flag true.
2. Verify full access to `exempt` grants `restricted` nothing on `enforced` or `inherits`.
3. Verify `writer`'s rule for `enforced` grants nothing on `inherits`.

## test_missing_collection_status_follows_database_flag

### Description

Test that existence masking follows the flag. An open database has nothing to hide, so a missing
collection is a 404. An enforcing database answers 403, so that users cannot discover which
keyspaces exist.

### Steps

1. Start Edge Server with root flag true.
2. Verify a missing collection on `exempt` is 404.
3. Verify a missing collection on `enforced` is 403.

## test_all_dbs_follows_database_flag

### Description

Test that `/_all_dbs` filtering follows the per-database flag. An open database is listed for
every user, and an enforcing database only for users with a rule for it.

### Steps

1. Start Edge Server with root flag true.
2. Verify `restricted` sees only `exempt`.
3. Verify `ruled` sees `enforced` and `exempt`, but not `inherits`.
4. Verify the admin sees every database.

## test_collections_and_queries

### Description

Test enforcement on named collections and on named queries, using
`test_per_db_access_control_travel.json`. `travel` (the travel dataset) is enforcing and `names`
(the names dataset) is exempt.

| Named query | Database | Access rule |
|---|---|---|
| `hotel_ids` | `travel` | none: any user who can read a collection in `travel` |
| `airline_ids` | `travel` | `allow.collections: ["travel.airlines"]` |
| `name_ids` | `names` | none |

| User | Access block |
|---|---|
| `hotel_reader` | `travel.travel.hotels: [read]`, `names._default._default: [read]` |
| `restricted` | `{}` |

Edge Server checks the keyspace in the URL before the query's own access rule. `/travel/_query/...`
targets `travel._default._default`, which `hotel_reader` cannot read, so its queries are called
through `travel.travel.hotels`. Access control applies to named queries only, so ad hoc queries are
not tested.

The `names._default._default` rule also checks that a fully qualified default-collection rule is
attributed to its database for the exemption warning.

### Steps

1. Start Edge Server with `travel` enforcing and `names` exempt, both with named queries.
2. Verify `hotel_reader` can only read `travel.hotels` in `travel`, and has full access to `names`.
3. Verify `restricted` is denied `travel.hotels` and has full access to `names`.
4. Verify the admin can run both `travel` named queries.
5. Verify `hotel_reader` can run `hotel_ids` through `travel.travel.hotels`, but not `airline_ids`.
6. Verify `restricted` can run neither `travel` query, and can run `name_ids` on `names`.
7. Verify Edge Server warned that rules for `names` are ignored.

## test_edge_to_edge_replication

### Description

Test that enforcement applies to replication in both directions. A consumer Edge Server runs six
replications against a provider with `enforced` true and `exempt` false:

| Replication | User | Expected |
|---|---|---|
| pull `enforced` | `ruled` | arrives |
| pull `enforced` | `restricted` | nothing |
| pull `exempt` | `restricted` | arrives |
| push to `enforced` | `writer` | arrives |
| push to `enforced` | `ruled` (read only) | nothing |
| push to `exempt` | `ruled` (rule ignored) | arrives |

Each refused replication has an allowed one against the same database, so a missing document
means a denial rather than a replication that hasn't caught up yet. Requires at least 2 Edge
Servers.

### Steps

1. Start the provider with `enforced` true and `exempt` false.
2. As admin, write `seed_enforced` and `seed_exempt` on the provider.
3. Start the consumer with three pull and three push replications.
4. On the consumer, write one document to each push database.
5. Wait for the allowed pulls: `ruled` from `enforced`, `restricted` from `exempt`.
6. Wait for the allowed pushes: `writer` to `enforced`, `ruled` to `exempt`.
7. Verify `restricted` pulled nothing from `enforced`.
8. Verify `ruled` (read only) pushed nothing to `enforced`.

## test_cbl_replication

### Description

Test that enforcement applies to Couchbase Lite replication. Each replication is one-shot, on the
default collection, against Edge Server with `enforced` true and `exempt` false.

Pull needs read access, and push needs read and write. A read-only user's connection is pull-only,
so a push-and-pull replicator from that user is refused outright (403, "Attempting to push to a
pull-only replicator"), rather than pulling and dropping the push.

Requires a CBL test server.

### Steps

1. Start Edge Server with `enforced` true and `exempt` false.
2. As admin, write `seed_enforced` and `seed_exempt`.
3. Push and pull `exempt` as `ruled`: its read-only rule is ignored.
4. Pull `enforced` as `ruled`: its read rule allows it.
5. Push and pull `enforced` as `ruled`: refused as pull-only, and nothing is pushed.
6. Push and pull `enforced` as `restricted`: the replicator fails and nothing moves.