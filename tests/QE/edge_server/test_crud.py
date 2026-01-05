from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass


class TestCrud(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_basic_information_retrieval(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("test_basic_information_retrieval")
        edge_server = cblpytest.edge_servers[0]
        self.mark_test_step("get server information")
        version = await edge_server.get_version()
        self.mark_test_step(f"VERSION:{version.raw}")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_database_config(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("test_database_config")
        edge_server = cblpytest.edge_servers[0]
        self.mark_test_step("fetch all databases")
        all_dbs = await edge_server.get_all_dbs()
        self.mark_test_step(f" Databases : {all_dbs}")
        db_name = all_dbs[0]
        self.mark_test_step("Fetch  database info")
        db_info = await edge_server.get_db_info(db_name)
        self.mark_test_step(f"Fetched  database info: {db_info}")
        assert db_info is not None