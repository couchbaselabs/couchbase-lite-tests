from cbltest import CBLPyTest
from cbltest.globals import CBLPyTestGlobal
import pytest

class TestResetDb:
    def setup_method(self, method):
        # If writing a new test do not forget this step or the test server
        # will not be informed about the currently running test
        CBLPyTestGlobal.running_test_name = method.__name__

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name", ["empty", "names", "posts", "todo", "travel"]
    )
    async def test_reset_db(self, cblpytest: CBLPyTest, name: str):
        db = await cblpytest.test_servers[0].create_and_reset_db(name, ["test"])
        assert db is not None