import asyncio
import json
import time
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.idleops import CommandCounts, document_commands, read_idle_op_snapshot, take_quiet_idle_op_snapshot
from cbltest.api.syncgateway import DatabaseConfig, IndexConfig, ISGRPayload, StartupConfigResponse, SyncGateway
from cbltest.logging import cbl_info
from cbltest.plugins.sgw_cluster_manager import SyncGatewayClusterManager

# Long enough for the background tasks that run every few minutes or hourly to run, not only the frequent ones.
# A run can set another time, in seconds, with this key in its --test-props file.
DEFAULT_IDLE_SECONDS = 90 * 60
IDLE_SECONDS_PROP = "idle_ops_seconds"

# The bootstrap config Capella gives Sync Gateway in a free tier App Service, the kind its idle-cluster hibernation
# check runs on. The AWS environment uploads it to every node, and start_local.py --capella-pft-bootstrap starts
# local nodes with its settings.
CAPELLA_PFT_BOOTSTRAP = "bootstrap-capella-pft"
CAPELLA_PFT_BOOTSTRAP_PATH = (
    Path(__file__).resolve().parents[3]
    / "environment"
    / "aws"
    / "sgw_setup"
    / "config"
    / f"{CAPELLA_PFT_BOOTSTRAP}.json"
)

# Scheduled tombstone compaction is the only background task that runs a query, so it runs as often as Sync Gateway
# allows (about every 58 minutes), rather than daily. Any idle time at least this long holds a run on every database.
COMPACT_INTERVAL_DAYS = 0.04
COMPACT_INTERVAL_SECONDS = COMPACT_INTERVAL_DAYS * 24 * 60 * 60

# Time for the work done while a database starts (index builds, DCP checkpoints, node registration) to finish,
# since that work is not idle.
SETTLE_SECONDS = 60

PROGRESS_INTERVAL_SECONDS = 300

# Quiet readings to take at each end of the idle time. The one Sync Gateway is furthest behind in is left out, in case
# a background task had paused before counting its operations.
QUIET_SAMPLES = 5


def _format_counts(counts: CommandCounts) -> str:
    return "\n".join(f"  {bucket} {opcode}: {count}" for (bucket, opcode), count in sorted(counts.items())) or "  none"


async def _runs_capella_pft_bootstrap(sg: SyncGateway) -> bool:
    """Whether a node was started with the unsupported options of CAPELLA_PFT_BOOTSTRAP, which only Capella sets."""
    expected = StartupConfigResponse.Unsupported.model_validate(
        json.loads(CAPELLA_PFT_BOOTSTRAP_PATH.read_text())["unsupported"]
    )
    actual = (await sg.get_startup_config()).unsupported
    return all(getattr(actual, field) == getattr(expected, field) for field in expected.model_fields_set)


def _database_config(bucket: str) -> DatabaseConfig:
    # Sync Gateway runs scheduled compaction only on nodes that import documents.
    return DatabaseConfig(
        bucket=bucket,
        index=IndexConfig(num_replicas=0),
        import_docs=True,
        compact_interval_days=COMPACT_INTERVAL_DAYS,
    )


@pytest.mark.standalone
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestSyncGatewayIdleOps(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_idle_ops_match_couchbase_server(
        self, cblpytest: CBLPyTest, sg_cluster_manager: SyncGatewayClusterManager
    ) -> None:
        idle_seconds = float(cblpytest.extra_props.get(IDLE_SECONDS_PROP, DEFAULT_IDLE_SECONDS))
        cluster = cblpytest.clusters[0]
        sync_gateways = cluster.sync_gateways
        couchbase_servers = cluster.couchbase_servers
        sg = sync_gateways[0]
        if await sg.using_rosmar:
            pytest.skip("Compares against Couchbase Server's own counts, so needs a Couchbase Server backing store")

        self.mark_test_step(
            f"Check that every Sync Gateway node runs with the settings of '{CAPELLA_PFT_BOOTSTRAP}', the bootstrap "
            "config of a Capella free tier App Service. If one does not, upload Couchbase Server's root CA "
            "certificate to every node, and restart every node with it."
        )
        if not all(await asyncio.gather(*(_runs_capella_pft_bootstrap(node) for node in sync_gateways))):
            self.skip_if_not(
                sg_cluster_manager.has_shell2http_sidecar,
                f"Sync Gateway does not run with the settings of '{CAPELLA_PFT_BOOTSTRAP}', and there is no shell2http "
                "sidecar on every node to restart it with them. Start a local environment with "
                "start_local.py --capella-pft-bootstrap",
            )
            await sg_cluster_manager.upload_certificate(
                cert_content=await couchbase_servers[0].get_root_ca_certificate(), cert_name="cbs-ca-cert.pem"
            )
            await sg_cluster_manager.restart_with_config(CAPELLA_PFT_BOOTSTRAP)

        bucket_name = "idle-ops-bucket"
        db_name = "idle_ops_db"
        self.mark_test_step(
            f"Create bucket '{bucket_name}' backed database '{db_name}', importing documents and compacting tombstones "
            f"every {COMPACT_INTERVAL_DAYS} days, and wait for it to be online."
        )
        await cluster.create_database(db_name, _database_config(bucket_name))

        remote_bucket_name = "idle-ops-remote-bucket"
        remote_db_name = "idle_ops_remote_db"
        self.mark_test_step(
            f"Create bucket '{remote_bucket_name}' backed database '{remote_db_name}' to replicate with, set up the "
            "same way, and wait for it to be online."
        )
        await cluster.create_database(remote_db_name, _database_config(remote_bucket_name))

        username = "isgr_user"
        password = "password"
        self.mark_test_step(f"Add user '{username}' to '{remote_db_name}', with access to channel 'isgr'.")
        await sg.add_user(
            remote_db_name,
            username,
            password,
            collection_access=sg.create_collection_access_dict({"_default._default": ["isgr"]}),
        )

        replication_id = "idle_ops_isgr"
        self.mark_test_step(
            f"Start a continuous pushAndPull replication '{replication_id}' from '{db_name}' to '{remote_db_name}', "
            f"signed in as '{username}', and wait for it to be running."
        )
        await sg.start_isgr(
            db_name,
            ISGRPayload(
                replication_id=replication_id,
                # The public port, since isgr_user is not an admin
                remote_url=sg.public_url,
                remote_db=remote_db_name,
                direction="pushAndPull",
                continuous=True,
                remote_username=username,
                remote_password=password,
            ),
        )
        await sg.wait_for_isgr_status(db_name, replication_id, "running")

        self.mark_test_step(f"Wait {SETTLE_SECONDS}s for the work of starting the databases and replication to finish.")
        await asyncio.sleep(SETTLE_SECONDS)

        self.mark_test_step(
            "Record the idle_kv_ops and idle_query_ops stats of every Sync Gateway node, and the commands, kv_ops and "
            "query requests of every Couchbase Server node, at a moment when none of them is moving."
        )
        start = await take_quiet_idle_op_snapshot(sync_gateways, couchbase_servers, samples=QUIET_SAMPLES)

        self.mark_test_step(
            f"Leave the databases idle for {idle_seconds:.0f}s: no documents change, and the replication is the only "
            "client."
        )
        end_time = time.monotonic() + idle_seconds
        while (remaining := end_time - time.monotonic()) > 0:
            await asyncio.sleep(min(PROGRESS_INTERVAL_SECONDS, remaining))
            # Not a quiet snapshot, so the counts can be a few operations apart.
            now = await read_idle_op_snapshot(sync_gateways, couchbase_servers)
            cbl_info(
                f"{max(end_time - time.monotonic(), 0):.0f}s left: Sync Gateway counted "
                f"{now.idle_kv_ops - start.idle_kv_ops} idle KV operations and "
                f"{now.idle_query_ops - start.idle_query_ops} idle queries, and Couchbase Server ran "
                f"{document_commands(now.commands - start.commands).total()} document commands, "
                f"{(now.kv_ops - start.kv_ops).total()} kv_ops and {now.query_requests - start.query_requests} queries"
            )

        self.mark_test_step(
            "Record the counters again. Check that the number of idle KV operations Sync Gateway counted is exactly "
            "the rise in Couchbase Server's kv_ops. Check that the number of idle queries Sync Gateway counted is "
            "exactly the number of queries Couchbase Server ran, and, if the idle time was at least one compaction "
            "interval, more than zero."
        )
        end = await take_quiet_idle_op_snapshot(sync_gateways, couchbase_servers, samples=QUIET_SAMPLES)
        idle_kv_ops = end.idle_kv_ops - start.idle_kv_ops
        idle_query_ops = end.idle_query_ops - start.idle_query_ops
        query_requests = end.query_requests - start.query_requests
        commands = end.commands - start.commands
        document_ops = document_commands(commands)
        kv_ops = end.kv_ops - start.kv_ops
        summary = (
            f"In {idle_seconds:.0f}s Sync Gateway counted {idle_kv_ops} idle KV operations, and Couchbase Server ran "
            f"{document_ops.total()} document commands and {kv_ops.total()} kv_ops.\n"
            f"Sync Gateway counted {idle_query_ops} idle queries, and Couchbase Server ran {query_requests} queries.\n"
            f"Document commands:\n{_format_counts(document_ops)}\n"
            f"kv_ops:\n{_format_counts(kv_ops)}\n"
            f"Other commands, not compared:\n{_format_counts(commands - document_ops)}"
        )
        cbl_info(summary)
        assert idle_kv_ops > 0, summary
        # Capella hibernates an idle cluster when its kv_ops, less Sync Gateway's idle_kv_ops, did not rise. Ops Sync
        # Gateway misses keep the cluster awake, and ops it counts beyond kv_ops would hide that many real ones.
        assert idle_kv_ops == kv_ops.total(), f"kv_ops less idle_kv_ops is {kv_ops.total() - idle_kv_ops}\n{summary}"
        if idle_seconds >= COMPACT_INTERVAL_SECONDS:
            # Each compaction runs at least one tombstone query on each collection.
            assert idle_query_ops > 0, summary
        assert idle_query_ops == query_requests, summary
