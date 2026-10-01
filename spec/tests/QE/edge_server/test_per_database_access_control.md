# Per-Database User Access Control Tests (Edge Server)

These tests validate the per-database `enable_user_access_control` flag (CBL-8556, Edge Server
1.1.1). A `databases.<name>` block may set the flag, and the existing root-level key becomes the
default for databases that don't. For database D the flag resolves to D's own key if present, else
the root key, else `false`.

Every test skips on Edge Server older than 1.1.1.

Common setup, used by every test:

- Each test writes its own users file to the Edge Server host, with bcrypt-hashed passwords, and
  points its config at it. The provisioned admin user is always included, with the `admin` role,
  so the harness can still manage the server.
- Every database is created empty (`create: true`) with client writes and client sync enabled.
- Console logging is on, so the Edge Server's startup messages land in `/home/ec2-user/log/edge.log`,
  which the tests read for startup errors and warnings.
- Access is probed over the REST API as each user: a **read** is `GET /{db}/_all_docs` and a
  **write** is `PUT /{db}/{new doc id}`. "Allow" means the request succeeds, and "deny" means 403.
  Any other status, a 401 in particular (the user failed to authenticate), is reported as an
  error in the test rather than read as either.
- A table-driven test checks every row before failing, and reports every mismatch together.

## test_flag_resolution

### Description

Test the resolution rule for every combination of root flag and database flag. The subject
database's flag is varied. A second, *anchor* database always sets `enable_user_access_control:
true`, so that access control is enabled somewhere and the probe user may carry an access block.

The probe user's only rule is read/write on the anchor database. On the subject database it
therefore has full access when the database is open, and is denied when it is enforcing.

| Case | Root | Subject database | Resolved |
|---|---|---|---|
| `row1_root_absent_db_absent` | &mdash; | &mdash; | open |
| `row2_root_absent_db_false` | &mdash; | false | open |
| `row3_root_absent_db_true` | &mdash; | true | enforcing |
| `row4_root_false_db_absent` | false | &mdash; | open |
| `row5_root_false_db_false` | false | false | open |
| `row6_root_false_db_true` | false | true | enforcing |
| `row7_root_true_db_absent` | true | &mdash; | enforcing |
| `row8_root_true_db_false` | true | false | open |
| `row9_root_true_db_true` | true | true | enforcing |

Row 7 is how every shipped 1.1 config looks. Row 8 is the only case where the database overrides
the root.

### Steps

1. Write a users file with the admin user and `prober`, whose only rule is read/write on `anchor_db`.
2. Start Edge Server with the case's root flag, `subject_db` with the case's flag, and `anchor_db` with `enable_user_access_control: true`.
3. Verify `prober` can read and write `anchor_db`. This proves it authenticates and its rules apply.
4. Verify `prober` is allowed to read and write `subject_db` when the case resolves open, and denied both when it resolves enforcing.
5. Verify the admin user can read and write `subject_db`.

## test_user_access_block_by_database

### Description

Test how a user's access block combines with each database's resolved flag (Rules 2 and 3), for
each kind of user, in one config. The test runs with the root flag absent (the requirement doc's
opt-in form) and with it `true` (the 1.1 form with one database exempted).

| Database | Flag | Resolved (root absent) | Resolved (root true) |
|---|---|---|---|
| `enforced_db` | true | enforcing | enforcing |
| `exempt_db` | false | open | open |
| `default_db` | &mdash; | open | enforcing |

| User | Access block |
|---|---|
| admin | none, `admin` role |
| `no_block` | none |
| `ruled` | `enforced_db: [read]`, `exempt_db: [read]` |
| `empty_block` | `{}` |

Expected (read / write):

| User | `enforced_db` | `exempt_db` | `default_db` open | `default_db` enforcing |
|---|---|---|---|---|
| admin | allow / allow | allow / allow | allow / allow | allow / allow |
| `no_block` | allow / allow | allow / allow | allow / allow | allow / allow |
| `ruled` | allow / **deny** | allow / **allow** | allow / allow | deny / deny |
| `empty_block` | deny / deny | allow / allow | allow / allow | deny / deny |

`ruled` writing to `exempt_db` despite a read-only rule is the check that an open database ignores
rules rather than evaluating them.

### Steps

1. Write a users file with the admin user, `no_block`, `ruled` and `empty_block`.
2. Start Edge Server with the case's root flag and the three databases.
3. As each user, read and write each database, and compare against the expected table for the case.

## test_startup_validation

### Description

Test that startup rejects access blocks that would silently fail open, and warns about a
deliberate exemption. The expected message fragments come from the Edge Server source.

| Case | Root | Databases | User's access block | Expected |
|---|---|---|---|---|
| `access_block_flag_nowhere` | &mdash; | `db1` &mdash; | `db1: [read]` | ERROR |
| `empty_access_block_flag_nowhere` | &mdash; | `db1` &mdash; | `{}` | ERROR |
| `rule_for_unset_db_root_absent` | &mdash; | `db1` true, `db2` &mdash; | `db1`, `db2` | ERROR |
| `rule_for_unset_db_root_false` | false | `db1` true, `db2` &mdash; | `db1`, `db2` | ERROR |
| `scoped_rule_for_unset_db` | &mdash; | `db1` true, `db2` &mdash; | `db1`, `db2.*` | ERROR |
| `rule_for_exempt_db_root_absent` | &mdash; | `db1` true, `db2` false | `db1`, `db2` | WARNING, starts |
| `rule_for_exempt_db_root_true` | true | `db1` &mdash;, `db2` false | `db1`, `db2` | WARNING, starts |
| `rule_for_inheriting_db_root_true` | true | `db1` &mdash;, `db2` &mdash; | `db1`, `db2` | starts, no warning |
| `wildcard_rule` | &mdash; | `db1` true, `db2` &mdash; | `*: [read]` | starts, no warning |

The two ERRORs about a rule for an unset database differ only in whether the root is absent or
explicitly `false`. Both fail, because neither leaves the database explicitly exempted.
`scoped_rule_for_unset_db` checks that a keyspace pattern is attributed to its database.
`wildcard_rule` checks that `*`, which names no database, is not attributed to one.

### Steps

1. Write a users file with the admin user and `subject`, holding the case's access block.
2. Start Edge Server with the case's config.
3. For an ERROR case, verify startup fails and the Edge Server's output names the problem.
4. For every other case, verify startup succeeds and the admin user can read each database.
5. Verify the exemption warning appears in the Edge Server's output for a WARNING case, and does not appear otherwise.

## test_replication_respects_database_flag

### Description

Test that per-database enforcement applies to replication as well as to REST. A *provider* Edge
Server serves `enforced_db` (flag `true`) and `open_db` (flag absent, root absent). A *consumer*
Edge Server pulls from it as two users at once:

| Replication | User | Expected |
|---|---|---|
| `open_db` &rarr; `open_copy` | `syncer` (`{}`) | documents arrive |
| `enforced_db` &rarr; `reader_copy` | `reader` (`enforced_db: [read]`) | documents arrive |
| `enforced_db` &rarr; `denied_copy` | `syncer` (`{}`) | no documents |

`reader_copy` is the control for `denied_copy`: it pulls the same documents from the same database
at the same time. Once they have arrived there, their absence from `denied_copy` is a denial, not a
replication that has yet to catch up.

Requires a topology with at least 2 Edge Servers.

### Steps

1. Write a users file on the provider with the admin user, `syncer` (`{}`) and `reader` (`enforced_db: [read]`), and start it with `enforced_db` true and `open_db` unset.
2. As admin, write 3 documents to each of `enforced_db` and `open_db` on the provider.
3. Start the consumer with the three pull replications above.
4. Wait for the `open_db` documents to reach `open_copy`.
5. Wait for the `enforced_db` documents to reach `reader_copy`.
6. Verify none of the `enforced_db` documents are in `denied_copy`.
