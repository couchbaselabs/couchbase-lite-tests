from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass

SCRIPT_DIR = str(Path(__file__).parent)


class TestAuthentication(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_basic_auth(self, cblpytest: CBLPyTest) -> None:
        self.mark_test_step("test_basic_auth")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="names", config_file=f"{SCRIPT_DIR}/config/test_basic_auth.json"
        )
        valid_auth = ("username8", "password8")
        invalid_auth = ("invalid_user", "wrong_password")

        #     testing valid auth
        self.mark_test_step("testing valid auth")
        await edge_server.add_user(name=valid_auth[0], password=valid_auth[1])
        await edge_server.set_auth(name=valid_auth[0], password=valid_auth[1])

        active_tasks = await edge_server.get_active_tasks()
        self.mark_test_step(f"Active Tasks: {active_tasks}")

        # testing invalid auth
        self.mark_test_step("testing invalid auth")
        await edge_server.set_auth(name=invalid_auth[0], password=invalid_auth[1])
        try:
            await edge_server.get_active_tasks()
        except Exception:
            self.mark_test_step("invalid auth failed as expected")
        self.mark_test_step("testing anonymous auth ")
        await edge_server.set_auth(auth=False)
        try:
            await edge_server.get_active_tasks()
        except Exception:
            self.mark_test_step("No auth failed as expected")
