import asyncio

import pytest
from cbltest import CBLPyTest
from cbltest.api.multipeer_replicator import MultipeerReplicator
from cbltest.api.replicator_types import ReplicatorCollectionEntry
from cbltest.globals import CBLPyTestGlobal


class TestMultipeerReplicator:
    def setup_method(self, method):
        # If writing a new test do not forget this step or the test server
        # will not be informed about the currently running test
        CBLPyTestGlobal.running_test_name = method.__name__

    @pytest.mark.asyncio(loop_scope="session")
    async def test_start_stop_multipeer(self, cblpytest: CBLPyTest) -> None:
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]
        multipeer = MultipeerReplicator(
            "couchtest", db, [ReplicatorCollectionEntry(["_default._default"])]
        )
        await multipeer.start()
        await asyncio.sleep(2)
        status = await multipeer.get_status()
        assert status is not None, "A started multipeer replicator should have a status"
        assert len(status.replicators) == 0, "Nothing should be found"
        await multipeer.stop()
