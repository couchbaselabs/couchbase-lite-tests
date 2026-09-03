from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblEdgeServerBadResponseError

SCRIPT_DIR = str(Path(__file__).parent)


@pytest.mark.min_edge_servers(1)
class TestAuthentication(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_basic_auth(self, cblpytest: CBLPyTest) -> None:
        self.mark_test_step("test_basic_auth")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="names", config_file=f"{SCRIPT_DIR}/config/test_basic_auth.json"
        )
        valid_auth = ("username8", "password8")
        invalid_auth = ("invalid_user", "wrong_password")

        self.mark_test_step("testing valid auth")
        async with cblpytest.edge_servers[0].create_user_client(valid_auth[0], valid_auth[1]) as valid_client:
            active_tasks = await valid_client.get_active_tasks()
            self.mark_test_step(f"Active Tasks: {active_tasks}")

        self.mark_test_step("testing invalid auth")
        async with edge_server.get_user_client(invalid_auth[0], invalid_auth[1]) as invalid_client:
            with pytest.raises(CblEdgeServerBadResponseError):
                await invalid_client.get_active_tasks()

        self.mark_test_step("testing anonymous auth ")
        async with edge_server.get_anonymous_client() as anonymous_client:
            with pytest.raises(CblEdgeServerBadResponseError):
                await anonymous_client.get_active_tasks()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_valid_tls_mtls(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("test_valid_tls")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="names", config_file=f"{SCRIPT_DIR}/config/test_tls_config.json"
        )
        self.mark_test_step("get server information with TLS")
        version = await edge_server.get_version()
        assert len(version.version) > 4, "invalid version fetched"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="names", config_file=f"{SCRIPT_DIR}/config/test_mtls_config.json"
        )
        self.mark_test_step("get server information with mTLS")
        version = await edge_server.get_version()
        assert len(version.version) > 4, "invalid version fetched"
