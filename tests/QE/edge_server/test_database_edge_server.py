import json
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass

SCRIPT_DIR = str(Path(__file__).parent)


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
        with open(config_path) as f:
            config = json.load(f)
        config["databases"]["db"]["create"] = True
        config["databases"]["db"]["collections"] = ["test"]
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)

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
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)
