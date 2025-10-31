import os
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.httpclient import HTTPClient


class TestAuthentication(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_valid_tls(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("test_valid_tls")
        edge_server = cblpytest.edge_servers[0]
        await edge_server.reset_db()
        file_path = os.path.abspath(os.path.dirname(__file__))
        file_path = str(Path(file_path, ".."))
        edge_server = await edge_server.set_config(
            f"{file_path}/environment/edge_server/config/test_tls_config.json",
            "/opt/couchbase-edge-server/etc/config.json",
        )
        self.mark_test_step("get server information")
        client = HTTPClient(cblpytest.http_clients[0], edge_server)
        await client.connect()
        await client.get_tls_certificate()
        version = await client.get_version()
        print(version)
        self.mark_test_step(f"VERSION:{version}")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_verify_mtls(self, cblpytest: CBLPyTest) -> None:
        self.mark_test_step("test_verify_mtls")
        edge_server = cblpytest.edge_servers[0]
        await edge_server.reset_db()
        file_path = os.path.abspath(os.path.dirname(__file__))
        file_path = str(Path(file_path, ".."))
        client = HTTPClient(cblpytest.http_clients[0], edge_server)
        await client.connect()
        await client.create_certificate()
        edge_server_new = await edge_server.set_config(
            f"{file_path}/environment/edge_server/config/test_mtls_config.json",
            "/opt/couchbase-edge-server/etc/config.json",
        )

        self.mark_test_step("get server information")
        client.edge_server = edge_server_new
        version = await client.get_version()
        print(version)
        self.mark_test_step(f"VERSION:{version}")

    @pytest.mark.asyncio
    async def test_basic_auth(self, cblpytest: CBLPyTest) -> None:
        self.mark_test_step("test_basic_auth")
        edge_server = cblpytest.edge_servers[0]
        await edge_server.reset_db()
        file_path = os.path.abspath(os.path.dirname(__file__))
        file_path = str(Path(file_path, ".."))
        edge_server_new = await edge_server.set_config(
            f"{file_path}/environment/edge_server/config/test_basic_auth.json",
            "/opt/couchbase-edge-server/etc/config.json",
        )
        valid_auth = ("username", "password")
        invalid_auth = ("invalid_user", "wrong_password")

        #     testing valid auth
        self.mark_test_step("testing valid auth")
        await edge_server_new.add_user(name=valid_auth[0], password=valid_auth[1])
        await edge_server_new.set_auth(name=valid_auth[0], password=valid_auth[1])
        client = HTTPClient(cblpytest.http_clients[0], edge_server_new)
        await client.connect()
        active_tasks = await client.get_active_tasks()
        self.mark_test_step(f"Active Tasks: {active_tasks}")

        # testing invalid auth
        self.mark_test_step("testing invalid auth")
        await edge_server_new.set_auth(name=invalid_auth[0], password=invalid_auth[1])
        try:
            await client.get_active_tasks()
        except Exception:
            self.mark_test_step("invalid auth failed as expected")
        self.mark_test_step("testing anonymous auth ")
        edge_server.set_auth(auth=False)
        try:
            await client.get_active_tasks()
        except Exception:
            self.mark_test_step("No auth failed as expected")
