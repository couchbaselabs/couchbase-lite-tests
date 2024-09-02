from pathlib import Path
from typing import Any, Callable, Dict, Optional
from cbltest import CBLPyTest
from cbltest.jsonhelper import json_equivalent
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database import Database
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (ReplicatorCollectionEntry, ReplicatorType, ReplicatorBasicAuthenticator,
                                          ReplicatorActivityLevel)

import pytest, pytest_asyncio

class TestQueryConsistency(CBLTestClass):
    __database: Optional[Database]

    @pytest_asyncio.fixture(autouse=True)
    async def setup_method_fixture(self, cblpytest: CBLPyTest, dataset_path: Path):
        if TestQueryConsistency.__database is not None:
            return
        
        # These tests do not modify the data in the bucket, so set it up here to avoid
        # needless teardown and re-setup
        cloud = CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])
        await cloud.configure_dataset(dataset_path, "travel")

        dbs = await cblpytest.test_servers[0].create_and_reset_db("travel", ["db1"])
        replicator = Replicator(dbs[0], cblpytest.sync_gateways[0].replication_url("travel"),
                                collections=[ReplicatorCollectionEntry(["travel.airlines", "travel.routes", "travel.landmarks",
                                                                        "travel.airports", "travel.hotels"])],
                                replicator_type=ReplicatorType.PUSH_AND_PULL,
                                authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                                pinned_server_cert=cblpytest.sync_gateways[0].tls_cert())
        await replicator.start()

        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, \
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        TestQueryConsistency.__database = dbs[0]

    async def _test_query(self, cblpytest: CBLPyTest, query: str, collection: str, sort: Optional[Callable[[Dict], str]] = None,
                         comparison: Callable[[Any, Any], bool] = json_equivalent):
        assert TestQueryConsistency.__database is not None, "Weird...setup not finished?"

        query_for_logging = query.format(f"travel.{collection}")
        self.mark_test_step(f"Run '{query_for_logging}' on test server")
        local_results = await self.__database.run_query(query_for_logging)

        self.mark_test_step(f"Run '{query_for_logging}' on Couchbase Server")
        remote_results = cblpytest.couchbase_servers[0].run_query(
            query, "travel", "travel", collection)
        
        self.mark_test_step("Check that the results are equivalent")
        if sort is not None:
            local_results.sort(key=sort)
            remote_results.sort(key=sort)

        assert comparison(local_results, remote_results)

    @pytest.mark.asyncio
    async def test_query_docids(self, cblpytest: CBLPyTest):
        # This is annoying because the sort algorithm is different between server and lite
        def id_sort(x: Dict):
            return x["id"]

        await self._test_query(
            cblpytest, 
            'SELECT meta().id FROM {} WHERE meta().id NOT LIKE "_sync%" ORDER BY id',
            "airlines",
            id_sort)

    @pytest.mark.asyncio
    async def test_any_operator(self, cblpytest: CBLPyTest):
        # This is annoying because the sort algorithm is different between server and lite
        def id_sort(x: Dict):
            return x["id"]

        await self._test_query(
            cblpytest,
            'SELECT meta().id FROM {} WHERE ANY departure IN schedule SATISFIES departure.utc > "23:41:00" END',
            "routes",
            id_sort)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("doc_id", [
        "airline_10",
        "doc_id_does_not_exist",
    ])
    async def test_select_star(self, cblpytest: CBLPyTest, doc_id: str):
        await self._test_query(
            cblpytest,
            f'SELECT * FROM {{}} WHERE meta().id = "{doc_id}"',
            "airlines")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("limit, offset", [
        (5, 5),
        (-5, -5)
    ])
    async def test_limit_offset(self, cblpytest: CBLPyTest, limit: int, offset: int):
        def comparison(left, right):
            return len(left) == len(right) and len(left) == max(0, limit)

        await self._test_query(
            cblpytest,
            f'SELECT meta().id FROM {{}} WHERE meta().id NOT LIKE "_sync%" LIMIT {limit} OFFSET {offset}',
            "airlines",
            comparison=comparison)

    @pytest.mark.asyncio
    async def test_query_where_and_or(self, cblpytest: CBLPyTest):
        await self._test_query(
            cblpytest,
            'SELECT meta().id FROM {} WHERE (country = "United States" OR country = "France") AND vacancy = true',
            "airlines")
        
    @pytest.mark.asyncio
    async def test_multiple_selects(self, cblpytest: CBLPyTest):
        # This is annoying because the sort algorithm is different between server and lite
        def id_sort(x: Dict):
            return x["id"]
        
        await self._test_query(
            cblpytest,
            'SELECT name, meta().id FROM {} WHERE country = "France"',
            "airlines",
            id_sort)
        
    @pytest.mark.asyncio
    @pytest.mark.parametrize("like_val", [
        "Royal Engineers Museum",
        "Royal engineers museum",
        "eng%e%",
        "Eng%e%",
        "%eng____r%",
        "%Eng____r%",
    ])
    async def test_query_pattern_like(self, cblpytest: CBLPyTest, like_val: str):
        # This is annoying because the sort algorithm is different between server and lite
        def id_sort(x: Dict):
            return x["id"]
        
        await self._test_query(
            cblpytest,
            f'SELECT meta().id, country, name FROM {{}} WHERE name LIKE "{like_val}"',
            "landmarks",
            id_sort)