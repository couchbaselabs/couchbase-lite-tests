import json
import os
from pathlib import Path

import pytest

from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass

class TestDatabase(CBLTestClass):

    @pytest.mark.asyncio(loop_scope="session")
    async def test_create_database(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("test_create_database")
        edge_server = cblpytest.edge_servers[0]
        file_path = os.path.abspath(os.path.dirname(__file__))
        file_path = str(Path(file_path, ".."))
        config_path = f"{file_path}/environment/edge_server/config/test_edge_server_with_multiple_rest_clients.json"
        edge_server = await edge_server.set_config(
            config_path,
            "/opt/couchbase-edge-server/etc/config.json"
        )
        dbs=await edge_server.get_all_dbs()
        assert len(dbs) == 1
    #     test write permission
        resp=await edge_server.add_document_auto_id({"test":"success"},db_name=dbs[0])
        assert resp.get("ok"), f"insert doc failed with resp {resp}"


    @pytest.mark.asyncio(loop_scope="session")
    async def test_edge_server_incorrect_db_config(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("test_edge_server_incorrect_db_config")
        edge_server = cblpytest.edge_servers[0]
        file_path = os.path.abspath(os.path.dirname(__file__))
        file_path = str(Path(file_path, ".."))
        config_path = f"{file_path}/environment/edge_server/config/test_edge_server_incorrect_db_config.json"
        try:
            edge_server = await edge_server.set_config(
                config_path,
                "/opt/couchbase-edge-server/etc/config.json"
            )
            await edge_server.get_version()
            assert False, "Edge server should have failed with incorrect config"
        except AssertionError:
            raise  # Re-raise assertion errors
        except Exception as e:
            self.mark_test_step(f"Edge server failed to get version as expected: {e}")
        with open(config_path, "r") as f:
            config = json.load(f)
        config["databases"]["db"]["create"]=True
        config["databases"]["db"]["collections"]=["test"]
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)

        edge_server = await edge_server.set_config(config_path, "/opt/couchbase-edge-server/etc/config.json")
        resp=await edge_server.get_db_info(db_name="db",collection="test")
        assert "test" in resp.get("collection_name"), "Collection not found"
        # REST API writes should fail
        try:
            await edge_server.add_document_auto_id({"readonly": {"key": "value"}}, "db", collection="test")
            assert False, "Edge server should have failed to add document"
        except AssertionError:
            raise  # Re-raise assertion errors
        except Exception as e:
            self.mark_test_step(f"Edge server failed to add document as expected: {e}")
        config["databases"]["db"]["create"] = False
        del config["databases"]["db"]["collections"]
        with open(config_path, "w") as file:
            json.dump(config, file, indent=4)