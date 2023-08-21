from cbltest import CBLPyTest
from cbltest.api.error import CblTestServerBadResponseError
from cbltest.api.error_types import ErrorDomain
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import ReplicatorActivityLevel
from cbltest.api.database import Database
from cbltest.globals import CBLPyTestGlobal
import pytest

class TestStartReplicator:
    def setup_method(self, method):
        # If writing a new test do not forget this step or the test server
        # will not be informed about the currently running test
        CBLPyTestGlobal.running_test_name = method.__name__

    @pytest.mark.asyncio
    async def test_invalid_database(self, cblpytest: CBLPyTest) -> None:
        repl = Replicator(Database(cblpytest.request_factory, 0, "fake"),
                          "ws://localhost:4984/db")
        with pytest.raises(CblTestServerBadResponseError, match="returned 400"):
            await repl.start()

    @pytest.mark.asyncio
    async def test_bad_endpoint(self, cblpytest: CBLPyTest) -> None:
        dbs = await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"])
        db = dbs[0]

        repl = Replicator(db, "ws://foo:4984/db")
        await repl.start()
        status = await repl.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is not None and ErrorDomain.equal(status.error.domain, ErrorDomain.CBL) \
            and status.error.code == 5002
        
        