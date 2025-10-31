import os
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.httpclient import HTTPClient
from deepdiff import DeepDiff


class TestQueryEdgeServer(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_named_queries(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Configuring named queries")
        edge_server = cblpytest.edge_servers[0]
        file_path = os.path.abspath(os.path.dirname(__file__))
        file_path = str(Path(file_path, "../.."))
        configured_server = await edge_server.set_config(
            f"{file_path}/environment/edge_server/config/test_named_queries.json",
            "/opt/couchbase-edge-server/etc/config.json",
        )

        self.mark_test_step("Testing valid parameterized query")
        client = HTTPClient(cblpytest.http_clients[0], configured_server)
        await client.connect()

        # Execute named query
        response = await client.named_query(
            db_name="names",
            name="user_by_email",
            params={
                "email": [
                    "jewel.macartney@nosql-matters.org",
                    "macartney@nosql-matters.org",
                ]
            },
        )
        self.mark_test_step(f"Query results: {response}")
        assert "name_144" in response.values()
        assert len(response["results"]) >= 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_adhoc_queries(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Enabling ad-hoc queries")
        edge_server = cblpytest.edge_servers[0]
        file_path = os.path.abspath(os.path.dirname(__file__))
        file_path = str(Path(file_path, "../.."))

        configured_server = await edge_server.set_config(
            f"{file_path}/environment/edge_server/config/test_named_queries.json",
            "/opt/couchbase-edge-server/etc/config.json",
        )

        client = HTTPClient(cblpytest.http_clients[0], configured_server)
        await client.connect()
        query = {
            "query": "SELECT name.first, name.last, gender, birthday, contact.email, contact.phone, contact.address.city, contact.address.state, likes FROM _default WHERE gender = $gender AND birthday BETWEEN $start_date AND $end_date AND ARRAY_CONTAINS(likes, $hobby) AND (ANY email IN contact.email SATISFIES email LIKE $email_filter END) AND contact.address.state = $state ORDER BY birthday ASC LIMIT 10",
            "params": {
                "gender": "female",
                "start_date": "1950-01-01",
                "end_date": "2000-12-31",
                "hobby": "driving",
                "email_filter": "%nosql-matters.org%",
                "state": "OH",
            },
        }
        expected_results = {
            "first": "Dorthey",
            "last": "Gracy",
            "gender": "female",
            "birthday": "1967-08-25",
            "email": ["dorthey.gracy@nosql-matters.org", "gracy@nosql-matters.org"],
            "phone": ["740-8360831"],
            "city": "Waldo",
            "state": "OH",
            "likes": ["snowboarding", "driving"],
        }

        self.mark_test_step("Executing ad-hoc query")
        response = await client.adhoc_query(
            db_name="names", query=query["query"], params=query["params"]
        )
        self.mark_test_step(f"Query result: {response}")
        assert DeepDiff(expected_results, response[0]) == {}

    @pytest.mark.asyncio
    async def test_negative_scenarios(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Testing negative scenarios")
        edge_server = cblpytest.edge_servers[0]
        file_path = os.path.abspath(os.path.dirname(__file__))
        file_path = str(Path(file_path, "../.."))

        # Configure with adhoc disabled
        configured_server = await edge_server.set_config(
            f"{file_path}/environment/edge_server/config/adhoc_disabled_config.json",
            "/opt/couchbase-edge-server/etc/config.json",
        )

        client = HTTPClient(cblpytest.http_clients[0], configured_server)
        await client.connect()

        self.mark_test_step("Testing missing parameters")
        response = await client.get(
            "/db/_query/named/user_by_email", raise_for_status=False
        )
        assert response.status == 400

        self.mark_test_step("Testing adhoc with disabled config")
        response = await client.post(
            "/db/_query",
            body={"statement": "SELECT 1"},
        )
        assert response.status == 403
