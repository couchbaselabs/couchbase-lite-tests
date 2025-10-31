import pytest
from cbltest import CBLPyTest
from cbltest.globals import CBLPyTestGlobal


class TestResetDb:
    def setup_method(self, method):
        # If writing a new test do not forget this step or the test server
        # will not be informed about the currently running test
        CBLPyTestGlobal.running_test_name = method.__name__

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("name", ["names", "posts", "todo", "travel"])
    async def test_reset_db(self, cblpytest: CBLPyTest, name: str):
        db = await cblpytest.test_servers[0].create_and_reset_db(["test"], dataset=name)
        assert db is not None

    @pytest.mark.asyncio(loop_scope="session")
    async def test_reset_empty(self, cblpytest: CBLPyTest):
        db = await cblpytest.test_servers[0].create_and_reset_db(["test"])
        assert db is not None

    @pytest.mark.asyncio(loop_scope="session")
    async def test_reset_empty_collections(self, cblpytest: CBLPyTest):
        db = await cblpytest.test_servers[0].create_and_reset_db(
            ["test"], collections=["a.b", "b.c", "c.d"]
        )
        assert db is not None
