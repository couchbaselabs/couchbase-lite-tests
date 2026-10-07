# Per-Database User Access Control Tests (Edge Server)

These tests validate the per-database `enable_user_access_control` flag (CBL-8556, Edge Server
1.1.1). For database D the flag resolves to D's own key, else the root key, else `false`. 
Each test writes its users to `/home/ec2-user/user/per_db_access_users.json`, always including the
admin `qe_admin`, and then starts Edge Server. Console logging is on, so startup errors and
warnings can be read from `/home/ec2-user/log/edge.log`. Over REST, a **read** is `_all_docs` and
a **write** is a `PUT`. A 403 is a denial, and any other failure fails the test.

Most tests use one of three configs. Each serves `enforced` (flag `true`), `exempt` (flag `false`)
and `inherits` (no flag), with anonymous access on:

| Config | Root flag | Resolution rows |
|---|---|---|
| `test_per_db_access_control.json` | `true` | 9, 8, 7 |
| `test_per_db_access_control_opt_in.json` | &mdash; | 3, 2, 1 |
| `test_per_db_access_control_root_false.json` | `false` | 6, 5, 4 |

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

Test that a database with no flag inherits a root flag of `true` (row 7, the form of every shipped
1.1 config).

### Steps

1. Start Edge Server with root flag true and `inherits` setting no flag.
2. Verify `restricted` and anonymous are denied `inherits`.
3. Verify `star` (`*`: read) is read-only on `inherits`.
4. Verify `no_block` has full access to `inherits`.

## test_database_set_true_enforces_rules

### Description

Test that a database setting `true` enforces each kind of access block (row 9, and the enforcing
column of the access-block table). A user with no access block gets an implicit full grant, a user
with rules gets exactly those rules, and a user with `{}` gets nothing. `write_only` covers a
write-only user on an enforcing database.

### Steps

1. Start Edge Server with root flag true and `enforced` setting true.
2. Verify the admin and `no_block` have full access to `enforced`.
3. Verify each user's rule applies on `enforced`: `ruled` is read-only, `writer` has full access, and `write_only` can write but not read.
4. Verify `restricted` and anonymous are denied `enforced`.

## test_database_set_false_ignores_rules

### Description

Test that a database setting `false` overrides a root of `true` (row 8). Rules are ignored, not
evaluated: a read-only user can write, a write-only user can read, and `{}` grants full access.

### Steps

1. Start Edge Server with root flag true and `exempt` setting false.
2. Verify every user, including anonymous, has full access to `exempt`.
3. Verify Edge Server warned that rules for `exempt` are ignored.

## test_opt_in_without_root_flag

### Description

Test the requirement doc's opt-in form, with no root key (rows 1&ndash;3). Only the database that
opts in is enforced. A database with no flag anywhere behaves as in 1.0, with every user having full
access.

### Steps

1. Start Edge Server with no root flag, `enforced` true, `exempt` false and `inherits` unset.
2. Verify only `enforced` restricts `restricted`.
3. Verify `ruled` is read-only on `enforced`.

## test_root_false_enforces_only_databases_set_true

### Description

Test that an explicit root `false` behaves like an absent one (rows 4&ndash;6).

### Steps

1. Start Edge Server with root flag false, `enforced` true, `exempt` false and `inherits` unset.
2. Verify only `enforced` restricts `restricted`.
3. Verify `ruled` is read-only on `enforced`.

## test_root_true_with_every_database_exempt

### Description

Test a root flag of `true` where every database opts out. A root of `true` enables access control
"somewhere", so access blocks are accepted, but no database enforces them.

### Steps

1. Start Edge Server with root flag true, and `exempt` and `exempt2` both false.
2. Verify `ruled` (`exempt: [read]`) and `restricted` (`{}`) have full access to both databases.
3. Verify Edge Server warned that rules for `exempt` are ignored.

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
collection is a 404. An enforcing database masks it as a 403.

### Steps

1. Start Edge Server with root flag true.
2. Verify a missing collection on `exempt` is 404.
3. Verify a missing collection on `enforced` is 403.

## test_unserved_database_is_masked

### Description

Test that a keyspace naming a database the server doesn't serve answers exactly like a forbidden
keyspace, so database existence can't be probed. There is no per-database flag for an unserved
database, so it falls back to the root flag, which is `true` here.

### Steps

1. Start Edge Server with root flag true.
2. Verify a database the server does not serve answers like a forbidden keyspace (both 403).

## test_all_dbs_follows_database_flag

### Description

Test that `/_all_dbs` filtering follows the per-database flag. An open database is listed for
every user, and an enforcing database only for users with a rule for it.

### Steps

1. Start Edge Server with root flag true.
2. Verify `restricted` sees only `exempt`.
3. Verify `ruled` sees `enforced` and `exempt`, but not `inherits`.
4. Verify the admin sees every database.

## Startup validation

Each of the following tests starts Edge Server with one user, `subject`, and asserts that startup
fails with the expected message from `UserAuth.cc`, naming the database where there is one.

### test_access_block_without_any_flag_fails_startup

1. Start Edge Server with no flag anywhere and a user with a rule for `db1`.
2. Verify startup fails, saying access control must be enabled.

### test_empty_access_block_without_any_flag_fails_startup

`{}` is an access block too, so it is refused when access control is enabled nowhere.

1. Start Edge Server with no flag anywhere and a user with an empty access block.
2. Verify startup fails, saying access control must be enabled.

### test_rule_for_unset_database_fails_startup

A rule for a database that is open only by default would silently fail open. An explicit `false`
is the way to say the database is meant to be open.

1. Start Edge Server with no root flag, `db1` true, `db2` unset, and a rule for `db2`.
2. Verify startup fails, naming `db2`.

### test_rule_for_unset_database_fails_startup_with_root_false

An explicit root `false` does not exempt a database. Only the database's own `false` does.

1. Start Edge Server with root flag false, `db1` true, `db2` unset, and a rule for `db2`.
2. Verify startup fails, naming `db2`.

### test_scope_wildcard_rule_is_attributed_to_its_database

1. Start Edge Server with no root flag, `db1` true, `db2` unset, and a `db2.*` rule.
2. Verify startup fails, naming `db2`.

### test_default_collection_rule_is_attributed_to_its_database

1. Start Edge Server with no root flag, `db1` true, `db2` unset, and a `db2._default._default` rule.
2. Verify startup fails, naming `db2`.

### test_passwordless_user_without_any_flag_fails_startup

A user may have no password (a certificate-only user) only once access control is enabled
somewhere.

1. Start Edge Server with only `db1` false and a user with no password.
2. Verify startup fails, saying the password is missing.

## test_startup_rejects_invalid_flag

### Description

Test that a malformed flag stops startup rather than being ignored. The flag is the string
`"true"`, `null`, or the number `1` on `db1`, or the misspelled key `enable_user_acess_control` on
`db1` or at the root. No user has an access block, so if Edge Server ignored the bad key it would
start, and `db1` would be open while its admin believed it was enforced.

### Steps

1. Start Edge Server with the case's bad key on `db1` or at the root.
2. Verify startup fails.

## test_collections_and_queries
### Steps

1. Start Edge Server with `travel` enforcing and `names` exempt, both with named queries.
2. Verify `hotel_reader` can only read `travel.hotels` in `travel`, and has full access to `names`.
3. Verify `restricted` is denied `travel.hotels` and has full access to `names`.
4. Verify the admin can run both `travel` named queries.
5. Verify `hotel_reader` can run `hotel_ids`, but not `airline_ids`.
6. Verify `restricted` can run neither `travel` query, and can run `name_ids` on `names`.
7. Verify Edge Server warned that rules for `names` are ignored.

## test_cert_only_user

### Description

Test a user with no password, which Edge Server allows once access control is enabled anywhere.
It authenticates with only its client certificate over mTLS. `test-client` is the common name of
the harness's provisioned client certificate.

### Steps

1. Start Edge Server over mTLS with `test-client` (no password, `enforced`: read).
2. Verify the certificate alone signs in as `test-client`, with its rules applied.

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

Test that enforcement applies to Couchbase Lite replication: a one-shot push-and-pull of the default
collection against Edge Server with `enforced` true and `exempt` false. Requires a CBL test server.

### Steps

1. Start Edge Server with `enforced` true and `exempt` false.
2. As admin, write `seed_enforced` and `seed_exempt`.
3. Push and pull `exempt` as `ruled`: its read-only rule is ignored.
4. Push and pull `enforced` as `ruled`: pull succeeds, push is refused.
5. Push and pull `enforced` as `restricted`: the replicator fails and nothing moves.
