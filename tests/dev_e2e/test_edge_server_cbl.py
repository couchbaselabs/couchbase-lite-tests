from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.replicator import Replicator, ReplicatorCollectionEntry, ReplicatorType
from cbltest.api.replicator_types import ReplicatorActivityLevel
from cbltest.configparser import EdgeServerInfo
from es_ws import assert_http_only_es_config, js_edge_replicator_url


@pytest.mark.min_test_servers(1)
@pytest.mark.min_edge_servers(1)
class TestEdgeServerCbl(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_js_push_to_edge_server_over_ws(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        config_path = EdgeServerInfo(cblpytest.config.edge_servers[0]).config_path
        assert_http_only_es_config(config_path)

        self.mark_test_step("Start HTTP Edge Server with an empty `db`")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="db", config_file=config_path
        )
        target = js_edge_replicator_url(edge_server, "db")

        self.mark_test_step("Reset local database")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]

        self.mark_test_step("Write three documents locally")
        async with db.batch_updater() as updater:
            for i in range(1, 4):
                updater.upsert_document(
                    "_default._default",
                    f"es_ws_{i}",
                    [{"type": "es-ws", "n": i}],
                )

        self.mark_test_step(f"Push to Edge Server over {target} (no pinned cert)")
        replicator = Replicator(
            db,
            target,
            replicator_type=ReplicatorType.PUSH,
            collections=[ReplicatorCollectionEntry(["_default._default"])],
        )
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Replicator error: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Verify documents on Edge Server REST")
        remote = await edge_server.get_all_documents("db")
        remote_ids = {row.id for row in remote.rows}
        assert {"es_ws_1", "es_ws_2", "es_ws_3"} <= remote_ids, (
            f"Missing pushed docs on ES: {sorted(remote_ids)}"
        )

        await cblpytest.test_servers[0].cleanup()
