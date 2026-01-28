import asyncio
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblEdgeServerBadResponseError
from deepdiff import DeepDiff  # pyright: ignore[reportMissingImports]

SCRIPT_DIR = str(Path(__file__).parent)


class TestQueryEdgeServer(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_named_queries(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Configuring named queries")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="names", config_file=f"{SCRIPT_DIR}/config/test_named_queries.json"
        )

        self.mark_test_step("Testing valid parameterized query")
        # Execute named query
        response = await edge_server.named_query(
            db_name="names",
            name="user_by_email",
            params={
                "email": "santo.mcclennan@nosql-matters.org",
                # "macartney@nosql-matters.org",
            },
        )
        self.mark_test_step(f"Query results: {response}")
        assert "name_11" in response[0].values()
        assert len(response) == 1

    @pytest.mark.asyncio(loop_scope="session")
    async def test_adhoc_queries(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Enabling ad-hoc queries")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="names", config_file=f"{SCRIPT_DIR}/config/test_named_queries.json"
        )
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
        response = await edge_server.adhoc_query(
            db_name="names", query=query["query"], params=query["params"]
        )
        self.mark_test_step(f"Query result: {response}")
        assert DeepDiff(expected_results, response[0]) == {}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_negative_scenarios(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Testing negative scenarios")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="names",
            config_file=f"{SCRIPT_DIR}/config/adhoc_disabled_config.json",
        )
        self.mark_test_step("Testing missing parameters")
        failed = False
        try:
            await edge_server.named_query(
                db_name="names",
                name="user_by_email",
            )
        except CblEdgeServerBadResponseError as e:
            failed = True
            assert "missing" in str(e).lower() or "error" in str(e).lower(), (
                f"Unexpected error for missing param: {e}"
            )
        assert failed
        self.mark_test_step("Testing adhoc with disabled config")
        failed = False
        try:
            await edge_server.adhoc_query(
                db_name="names", query="SELECT * FROM _default"
            )
        except CblEdgeServerBadResponseError as e:
            failed = True
            print(e)
            assert "forbidden" in str(e).lower() or "403" in str(e), (
                f"Unexpected error for adhoc disabled: {e}"
            )
        assert failed

    @pytest.mark.asyncio(loop_scope="session")
    async def test_query_on_expired_doc(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Configuring named queries")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="names", config_file=f"{SCRIPT_DIR}/config/test_named_queries.json"
        )

        self.mark_test_step("Create document that expire after 30 seconds")
        new_doc = {
            "birthday": "1954-06-29",
            "name": {"first": "Tonita", "last": "Rowman"},
            "contact": {
                "email": [
                    "tonita.rowman@nosql-matters.org",
                    "rowman@nosql-matters.org",
                ],
                "phone": ["724-7593085"],
                "region": "724",
                "address": {
                    "state": "PA",
                    "street": "16 Pratt Rd",
                    "zip": "15685",
                    "city": "Southwest",
                },
            },
            "gender": "female",
            "memberSince": "2008-06-14",
            "likes": [],
        }

        resp = await edge_server.add_document_auto_id(new_doc, "names", ttl=30)
        print(resp)
        await asyncio.sleep(30)
        # Execute named query
        response = await edge_server.named_query(
            db_name="names",
            name="user_by_email",
            params={"email": "tonita.rowman@nosql-matters.org"},
        )
        self.mark_test_step(f"Query results: {response}")
        assert len(response) == 0

    @pytest.mark.asyncio(loop_scope="session")
    async def test_adhoc_queries_incorrect_field(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Enabling ad-hoc queries")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            db_name="names", config_file=f"{SCRIPT_DIR}/config/test_named_queries.json"
        )

        query = {
            "query": "SELECT first, name.last, gender, birthday, contact.email, contact.phone, contact.address.city, contact.address.state, likes FROM _default WHERE gender = $gender AND birthday BETWEEN $start_date AND $end_date AND ARRAY_CONTAINS(likes, $hobby) AND (ANY email IN contact.email SATISFIES email LIKE $email_filter END) AND contact.address.state = $state ORDER BY birthday ASC LIMIT 10",
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
        response = await edge_server.adhoc_query(
            db_name="names", query=query["query"], params=query["params"]
        )
        self.mark_test_step(f"Query result: {response}")
        assert DeepDiff(expected_results, response[0]) == {}
