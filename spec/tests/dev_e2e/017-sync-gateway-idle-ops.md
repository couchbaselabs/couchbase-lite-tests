# Test Cases

## #1 test_idle_ops_match_couchbase_server

### Description

Checks that Sync Gateway's `idle_kv_ops` stat counts every KV operation that an
idle node makes. An idle node has databases but no changing documents, so all
the KV operations it makes come from background work: polling for config
changes, heartbeats, checking on other nodes, and reporting the status of
inter-Sync Gateway replications. The test sets up two databases with an idle,
continuous replication between them, and leaves them for a long time. It then
checks that the stat rose by exactly as much as Couchbase Server's `kv_ops` in
the same period. It also checks that Sync Gateway's `idle_query_ops` stat is
exactly the number of queries Couchbase Server ran.

These are the checks that Capella's idle-cluster hibernation makes: a cluster
with App Services is idle when its `kv_ops`, less Sync Gateway's
`idle_kv_ops`, did not rise, and the same for `n1ql_requests` less
`idle_query_ops`. An operation Sync Gateway misses keeps an idle cluster
awake. An operation it counts that `kv_ops` does not would hide one real
operation, so the two must match exactly, not only by at least. `kv_ops`
folds several commands into one op, for example ADD and REPLACE into `set`
and TOUCH into `get`, and it leaves some out: UNLOCK_KEY, OBSERVE, and a
subdoc command that fails on the whole document, such as on a CAS mismatch or
a missing document. Sync Gateway leaves those out of `idle_kv_ops` too.

The only background work that runs a query is scheduled tombstone compaction.
It runs every `compact_interval_days` (1 day by default) on each database of
each node that imports documents, and counts one idle query for each tombstone
query: one for each collection, and one more for each full batch of 250
tombstones. The first run is one interval after the database starts. So both
databases import documents and set `compact_interval_days` to 0.04, the lowest
value Sync Gateway allows, which is about 58 minutes. Any idle time at least
that long holds a run on every database, so the test then also checks that
the stat rose. Couchbase Server counts the queries it runs in the
`n1ql_requests` series of each node's `GET /metrics`, which counts every
request from every client.

The test leaves the databases idle for 1.5 hours, so it is marked `standalone`
and runs only when the command line names it, for example
`syncgateway/test_idle_ops.py`. A run of the whole suite skips it. A shorter
or longer time, in seconds, can be set with `idle_ops_seconds` in the
`--test-props` file. The test also needs a Couchbase Server backing store,
since rosmar has no command counts to compare against.

Every Sync Gateway node runs with the settings of `bootstrap-capella-pft`,
the bootstrap config that Capella gives a node of a free tier App Service,
since that is where Capella's hibernation check runs. Its settings are the same as
Capella's, so database configs are kept in xattrs, metadata goes in the
`_system._mobile` collection (Sync Gateway 4.1 and later, as in Capella), the
config poll runs at its default rate, and logging and the audit info provider
are set up as in Capella. It keeps only the parts the test environment needs:
username and password auth to Couchbase Server, where Capella uses x509
client certificates, and the environment's certificate and log paths. It
binds no metrics or diagnostic port beyond the defaults.

A node runs with those settings if its unsupported options match the
config's, which only Capella sets. A local environment started with
`start_local.py --capella-pft-bootstrap` already does. Otherwise the test
restarts every node with the config, which needs the shell2http sidecar on
every node, as in the AWS environment, so the test is skipped without it.
After a restart, the `sg_cluster_manager` fixture restarts every node with
the default bootstrap config again.

Capella does not use the commands that Couchbase Server runs, so the test
does not check them. It records them only to explain a failure, since
`kv_ops` folds commands together: Couchbase Server counts them, by bucket and
opcode, in the `kv_cmd_duration_seconds_count` series of each node's
`GET /metrics`. The commands that read or write a document are listed apart
from those that set up a connection, stream DCP, manage collections, or
report state, such as `HELLO`, `DCP_*`, `COLLECTIONS_*`, `STAT` and
`GET_ALL_VB_SEQNOS`, and from commands sent before a connection selects a
bucket. Couchbase Server sends some of these itself.

The counts are compared over the whole cluster: every Sync Gateway node and
every Couchbase Server node in the config, across every bucket. Sync Gateway
checks every bucket in the cluster for configs, not only the buckets of its
databases. Nothing else may use the cluster while the test runs, including a
Sync Gateway that is not in the config, because its KV operations and
queries would be counted by Couchbase Server but not by the stats.

Sync Gateway counts the KV operations of a background task when the task
ends. A reading taken while a task is running would include operations that
Couchbase Server has run but Sync Gateway has not counted yet. So each
reading of the counters is kept only if none of them moved for a short quiet
period around it. Each node reads `kv_ops` a moment before its command counts,
so `kv_ops` is watched too, and so are the query counts. A task that pauses between its last operation and
its end can still look quiet, so five quiet readings are taken at each end,
half a second apart, and the one with the fewest commands that Sync Gateway
has not counted is kept. A task that has not been counted can only add to
those.

### Steps

1. Check that every Sync Gateway node runs with the settings of
   `bootstrap-capella-pft`, the bootstrap config of a Capella free tier App
   Service. If one does not, upload Couchbase Server's root CA certificate to
   every node, and restart every node with it.
2. Create a bucket-backed database that imports documents and compacts
   tombstones every 0.04 days, and wait for it to be online.
3. Create a second bucket-backed database to replicate with, set up the same
   way, and wait for it to be online.
4. Add a user to the second database, with access to a channel.
5. Start a continuous pushAndPull replication from the first database to the
   second, signed in as that user, and wait for it to be running.
6. Wait for the work of starting the databases and replication to finish.
7. Record the `idle_kv_ops` and `idle_query_ops` stats of every Sync Gateway
   node, and the commands, `kv_ops` and query requests of every Couchbase
   Server node, at a moment when none of them is moving.
8. Leave the databases idle for the requested time: no documents change, and
   the replication is the only client.
9. Record the counters again. Check that the number of idle KV operations
   Sync Gateway counted is exactly the rise in Couchbase Server's `kv_ops`.
   Check that the number of idle queries Sync Gateway counted is exactly the
   number of queries Couchbase Server ran, and, if the idle time was at least
   one compaction interval, more than zero.
