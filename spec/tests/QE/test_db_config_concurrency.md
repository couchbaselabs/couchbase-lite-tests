# Database Config Concurrency Tests

Every database config update makes Sync Gateway reload the database, even an update that changes nothing.
These tests send config updates, deletes and recreates of one database to random Sync Gateway nodes at the same
time, while other requests read the database on every node. The order the requests run in is not fixed, so a run
is not deterministic. Each run logs its seed, and setting `db_config_concurrency_seed` in the `--test-props` file
replays the operations each writer picked, not the nodes they went to or the timing.

Every request must return within 30 seconds, because App Services times out requests after 30 seconds. No request
may return a 500, and each operation may only return the statuses listed for it. A failure lists every request
that broke these rules, so it can be classified rather than stopping at the first one.

The test runs with admin API authentication on, as on AWS, so Sync Gateway answers a request for a database it does
not serve with 403 rather than 404. An upsert config can still get 404 when the node serves the database but
another node has already deleted its config from the bucket. `GET /posts/` returns 200 in every database state,
including Starting and Stopping.

## test_concurrent_db_config_operations

Writers pick these operations at random, by weight:

| Operation | Request | Weight | Allowed statuses |
|---|---|---|---|
| upsert config | `POST /posts/_config` with the config the database started with | 4 | 201, 403, 404 |
| recreate database | `PUT /posts/` with the config the database started with | 2 | 201, 412 |
| delete database | `DELETE /posts/` | 1 | 200, 403 |

Readers send these to every node in turn:

| Operation | Request | Allowed statuses |
|---|---|---|
| get database | `GET /posts/` | 200, 403 |
| get all databases | `GET /_all_dbs` | 200 |

1. Configure the `posts` dataset on the Sync Gateway cluster
2. Read the config of the database, to send with the upsert config and recreate database operations
3. On every node, start a reader that sends the reader operations until the writers finish
4. Start 4 writers, each sending 15 operations to random nodes
5. Wait for the writers to finish, then stop the readers
6. Leave the database online with the config it started with, and wait for every node to run that config
7. Check that every request returned within 30 seconds with a status its operation allows, and that none returned a 500
