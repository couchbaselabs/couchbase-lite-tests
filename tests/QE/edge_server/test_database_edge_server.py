from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.asyncfile import read_json_file, write_json_file

SCRIPT_DIR = str(Path(__file__).parent)


@pytest.mark.min_edge_servers(1)
class TestDatabase(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_server_incorrect_db_config(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("test_edge_server_incorrect_db_config")
        config_path = f"{SCRIPT_DIR}/config/test_edge_server_incorrect_db_config.json"
        try:
            edge_server = await cblpytest.edge_servers[0].configure_dataset(
                config_file=config_path
            )
            await edge_server.get_version()
        except Exception:
            self.mark_test_step("Edge server failed to get version as expected")
        config = await read_json_file(config_path)
        config["databases"]["db"]["create"] = True
        config["databases"]["db"]["collections"] = ["test"]
        await write_json_file(config_path, config)

        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=config_path
        )
        resp = await edge_server.get_db_info(db_name="db", collection="test")
        assert "test" in resp.get("collection_name"), "Collection not found"
        # REST API writes should fail
        try:
            response = await edge_server.add_document_auto_id(
                {"readonly": {"key": "value"}}, "db", collection="test"
            )
            print(response)
        except Exception:
            self.mark_test_step("Edge server failed to add document as expected")
        config["databases"]["db"]["create"] = False
        del config["databases"]["db"]["collections"]
        await write_json_file(config_path, config)
