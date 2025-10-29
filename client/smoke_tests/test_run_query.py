import pytest
from cbltest import CBLPyTest
from cbltest.globals import CBLPyTestGlobal


class TestRunQuery:
    def setup_method(self, method):
        # If writing a new test do not forget this step or the test server
        # will not be informed about the currently running test
        CBLPyTestGlobal.running_test_name = method.__name__

    @pytest.mark.asyncio(loop_scope="session")
    async def test_run_query(self, cblpytest: CBLPyTest):
        db = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="names"
        )
        results = await db[0].run_query(
            "select meta().id from _ ORDER BY meta().id LIMIT 5"
        )
        assert results is not None, "The query should return a result"
        assert len(results) == 5, "The query should return five results"
        i = 1
        expected = ["name_1", "name_10", "name_100", "name_11", "name_12"]
        for i, r in enumerate(results):
            assert "id" in r, "The result should have an ID column"
            assert r["id"] == expected[i], f"The result ID should be {expected[i]}"
