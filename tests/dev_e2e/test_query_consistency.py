from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database import Database
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.jsonhelper import json_equivalent


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestQueryConsistency(CBLTestClass):
    __database: Database | None = None

    @pytest_asyncio.fixture(autouse=True)
    async def setup_method_fixture(self, cblpytest: CBLPyTest, dataset_path: Path):
        if TestQueryConsistency.__database is not None:
            return

        # These tests do not modify the data in the bucket, so set it up here to avoid
        # needless teardown and re-setup
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel")

        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        replicator = Replicator(
            dbs[0],
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[
                ReplicatorCollectionEntry(
                    [
                        "travel.airlines",
                        "travel.routes",
                        "travel.landmarks",
                        "travel.airports",
                        "travel.hotels",
                    ]
                )
            ],
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        status = await replicator.wait_for(
            ReplicatorActivityLevel.STOPPED, timeout=timedelta(seconds=300)
        )
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        TestQueryConsistency.__database = dbs[0]

    async def _test_query(
        self,
        cblpytest: CBLPyTest,
        query: str,
        collection: str,
        sort: Callable[[dict], str] | None = None,
        comparison: Callable[[Any, Any], bool] = json_equivalent,
    ):
        assert TestQueryConsistency.__database is not None, (
            "Weird...setup not finished?"
        )

        query_for_logging = query.format(f"travel.{collection}")
        self.mark_test_step(f"Run '{query_for_logging}' on test server")
        local_results = await TestQueryConsistency.__database.run_query(
            query_for_logging
        )

        self.mark_test_step(f"Run '{query_for_logging}' on Couchbase Server")
        remote_results = cblpytest.couchbase_servers[0].run_query(
            query, "travel", "travel", collection
        )

        self.mark_test_step("Check that the results are equivalent")
        if sort is not None:
            local_results.sort(key=sort)
            remote_results.sort(key=sort)

        assert comparison(local_results, remote_results)

    async def _test_join(
        self, cblpytest: CBLPyTest, query: str, server_query: str | None = None
    ):
        assert TestQueryConsistency.__database is not None, (
            "Weird...setup not finished?"
        )

        if server_query is None:
            server_query = query.replace("travel", "travel.travel")

        self.mark_test_step(f"Run '{query}' on test server")
        local_results = await TestQueryConsistency.__database.run_query(query)

        # All of the join tests involve both airlines and routes.  Currently I can
        # only choose one, but the others should be set up by now do to previous tests
        # If running this test standalone, you may need to CREATE PRIMARY INDEX
        # on both the airlines and routes collections.
        self.mark_test_step(f"Run '{server_query}' on Couchbase Server")
        remote_results = cblpytest.couchbase_servers[0].run_query(
            server_query, "travel", "travel", "airlines"
        )

        assert json_equivalent(local_results, remote_results)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_query_docids(self, cblpytest: CBLPyTest):
        # This is annoying because the sort algorithm is different between server and lite
        def id_sort(x: dict):
            return x["id"]

        await self._test_query(
            cblpytest,
            'SELECT meta().id FROM {} WHERE meta().id NOT LIKE "_sync%" ORDER BY id',
            "airlines",
            id_sort,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_any_operator(self, cblpytest: CBLPyTest):
        # This is annoying because the sort algorithm is different between server and lite
        def id_sort(x: dict):
            return x["id"]

        await self._test_query(
            cblpytest,
            'SELECT meta().id FROM {} WHERE ANY departure IN schedule SATISFIES departure.utc > "23:41:00" END',
            "routes",
            id_sort,
        )

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "doc_id",
        [
            "airline_10",
            "doc_id_does_not_exist",
        ],
    )
    async def test_select_star(self, cblpytest: CBLPyTest, doc_id: str):
        await self._test_query(
            cblpytest, f'SELECT * FROM {{}} WHERE meta().id = "{doc_id}"', "airlines"
        )

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("limit, offset", [(5, 5), (-5, -5)])
    async def test_limit_offset(self, cblpytest: CBLPyTest, limit: int, offset: int):
        def comparison(left, right):
            return len(left) == len(right) and len(left) == max(0, limit)

        await self._test_query(
            cblpytest,
            f'SELECT meta().id FROM {{}} WHERE meta().id NOT LIKE "_sync%" LIMIT {limit} OFFSET {offset}',
            "airlines",
            comparison=comparison,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_query_where_and_or(self, cblpytest: CBLPyTest):
        # This is annoying because the sort algorithm is different between server and lite
        def id_sort(x: dict):
            return x["id"]

        await self._test_query(
            cblpytest,
            'SELECT meta().id FROM {} WHERE (country = "United States" OR country = "France") AND vacancy = true',
            "hotels",
            id_sort,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_multiple_selects(self, cblpytest: CBLPyTest):
        # This is annoying because the sort algorithm is different between server and lite
        def id_sort(x: dict):
            return x["id"]

        await self._test_query(
            cblpytest,
            'SELECT name, meta().id FROM {} WHERE country = "France"',
            "hotels",
            id_sort,
        )

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "like_val",
        [
            "Royal Engineers Museum",
            "Royal engineers museum",
            "eng%e%",
            "Eng%e%",
            "%eng____r%",
            "%Eng____r%",
        ],
    )
    async def test_query_pattern_like(self, cblpytest: CBLPyTest, like_val: str):
        # This is annoying because the sort algorithm is different between server and lite
        def id_sort(x: dict):
            return x["id"]

        await self._test_query(
            cblpytest,
            f'SELECT meta().id, country, name FROM {{}} WHERE name LIKE "{like_val}"',
            "landmarks",
            id_sort,
        )

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "regex",
        ["\\bEng.*e\\b", "\\beng.*e\\b"],
    )
    async def test_query_pattern_regex(self, cblpytest: CBLPyTest, regex: str):
        # This is annoying because the sort algorithm is different between server and lite
        def id_sort(x: dict):
            return x["id"]

        await self._test_query(
            cblpytest,
            f'SELECT meta().id, country, name FROM {{}} t WHERE REGEXP_CONTAINS(t.name, "{regex}")',
            "landmarks",
            id_sort,
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_query_is_not_valued(self, cblpytest: CBLPyTest):
        await self._test_query(
            cblpytest,
            'SELECT meta().id, name FROM {} WHERE meta().id NOT LIKE "_sync%" and (name IS NULL OR name IS MISSING) ORDER BY name ASC LIMIT 100',
            "hotels",
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_query_ordering(self, cblpytest: CBLPyTest):
        await self._test_query(
            cblpytest,
            'SELECT meta().id, title FROM {} WHERE type = "hotel" ORDER BY name ASC',
            "hotels",
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_query_substring(self, cblpytest: CBLPyTest):
        await self._test_query(
            cblpytest,
            'SELECT meta().id, email, UPPER(name) from {} t where CONTAINS(t.email, "gmail.com")',
            "landmarks",
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_query_join(self, cblpytest: CBLPyTest):
        query = """SELECT DISTINCT airlines.name, airlines.callsign, routes.destinationairport, routes.stops, routes.airline
                   FROM travel.routes as routes
                    JOIN travel.airlines AS airlines
                    ON routes.airlineid = meta(airlines).id
                   WHERE routes.sourceairport = "SFO"
                   ORDER BY meta(routes).id
                   LIMIT 2"""

        server_query = """SELECT DISTINCT airlines.name, airlines.callsign, routes.destinationairport, routes.stops, routes.airline
                   FROM travel.travel.routes as routes
                    JOIN travel.travel.airlines AS airlines
                    ON KEYS routes.airlineid
                   WHERE routes.sourceairport = "SFO"
                   ORDER BY meta(routes).id
                   LIMIT 2"""

        await self._test_join(cblpytest, query, server_query)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_query_inner_join(self, cblpytest: CBLPyTest):
        query = """
            SELECT routes.airline, routes.sourceairport, airports.country
            FROM travel.routes as routes
             INNER JOIN travel.airports AS airports
             ON airports.icao = routes.destinationairport
            WHERE airports.country = "United States"
             AND routes.stops = 0
            ORDER BY routes.sourceairport
        """

        await self._test_join(cblpytest, query)

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "server_join_type",
        ["LEFT JOIN", "LEFT OUTER JOIN"],
    )
    async def test_query_left_join(self, cblpytest: CBLPyTest, server_join_type: str):
        query = """
            SELECT airlines, routes
            FROM travel.routes AS routes
             LEFT JOIN travel.airlines AS airlines
             ON meta(airlines).id = routes.airlineid
            ORDER BY meta(routes).id
            LIMIT 10
        """

        server_query = f"""
            SELECT airlines, routes
            FROM travel.travel.routes
             {server_join_type} travel.travel.airlines
             ON KEYS routes.airlineid
            WHERE meta(routes).id NOT LIKE "_sync%"
            ORDER BY meta(routes).id
            LIMIT 10
        """

        await self._test_join(cblpytest, query, server_query)

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "operation",
        ["=", "!="],
    )
    async def test_equality(self, cblpytest: CBLPyTest, operation: str):
        await self._test_query(
            cblpytest,
            f'SELECT meta().id, name FROM {{}} WHERE country {operation} "France" ORDER BY meta().id ASC',
            "airports",
        )

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "operation",
        [">", ">=", "<", "<="],
    )
    async def test_comparison(self, cblpytest: CBLPyTest, operation: str):
        await self._test_query(
            cblpytest,
            f"SELECT meta().id FROM {{}} WHERE geo.alt {operation} 1000 ORDER BY meta().id ASC",
            "airports",
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_in(self, cblpytest: CBLPyTest):
        await self._test_query(
            cblpytest,
            'SELECT meta().id FROM {} WHERE (country IN ["United States", "France"]) ORDER BY meta().id ASC',
            "airports",
        )

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "keyword",
        ["BETWEEN", "NOT BETWEEN"],
    )
    async def test_between(self, cblpytest: CBLPyTest, keyword: str):
        await self._test_query(
            cblpytest,
            f"SELECT meta().id FROM {{}} WHERE geo.alt {keyword} 100 and 200 ORDER BY meta().id ASC",
            "airports",
        )

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "keyword",
        ["IS", "IS NOT"],
    )
    async def test_same(self, cblpytest: CBLPyTest, keyword: str):
        await self._test_query(
            cblpytest,
            f"SELECT meta().id FROM {{}} WHERE iata {keyword} null ORDER BY meta().id ASC",
            "airports",
        )
