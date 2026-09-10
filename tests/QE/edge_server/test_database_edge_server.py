from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblEdgeServerBadResponseError, CblTestError
from cbltest.asyncfile import read_json_file, write_json_file

SCRIPT_DIR = str(Path(__file__).parent)


@pytest.mark.min_edge_servers(1)
class TestDatabase(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_server_incorrect_db_config(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        self.mark_test_step("test_edge_server_incorrect_db_config")
        config_path = f"{SCRIPT_DIR}/config/test_edge_server_incorrect_db_config.json"
        self.mark_test_step("Edge server should fail to serve a database it is not allowed to create.")
        # No db.cblite2 is provisioned, so with create=false the process dies and the sidecar 500s.
        with pytest.raises(CblTestError, match="failed to start"):
            await cblpytest.edge_servers[0].configure_dataset(config_file=config_path)
        config = await read_json_file(config_path)
        config["databases"]["db"]["create"] = True
        config["databases"]["db"]["collections"] = ["test"]
        config_path = str(tmp_path / "es_config.json")
        await write_json_file(config_path, config)

        edge_server = await cblpytest.edge_servers[0].configure_dataset(config_file=config_path)
        resp = await edge_server.get_db_info(db_name="db", collection="test")
        assert "test" in resp["collection_name"], "Collection not found"
        self.mark_test_step("REST API writes should fail against a read-only collection.")
        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.add_document_auto_id({"readonly": {"key": "value"}}, "db", collection="test")
