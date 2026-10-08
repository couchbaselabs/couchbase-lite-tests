from collections.abc import Awaitable
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.edgeservermanager import EdgeServerManager
from cbltest.api.error import CblEdgeServerBadResponseError
from cbltest.api.syncgateway import get_basic_auth_headers

SCRIPT_DIR = Path(__file__).parent
CONFIG = str(SCRIPT_DIR / "config" / "test_access_control.json")
USERS = SCRIPT_DIR / "config" / "test_access_control_users.json"
# The config reads its own users file, so the provisioned users.json never gains an access block.
USERS_FILE = "/home/ec2-user/user/access_control_users.json"
PASSWORD = "password"


async def _rows(request: Awaitable[list]) -> list | None:
    """The rows a query returned, or None if it was refused with 403.  Any other failure is a test error."""
    try:
        return await request
    except CblEdgeServerBadResponseError as e:
        assert e.code == 403, f"Expected a query result or 403, got {e.code}"
        return None


@pytest.mark.min_edge_servers(1)
class TestQueryAccessControl(CBLTestClass):
    async def _start(self, es: EdgeServerManager) -> EdgeServer:
        """Start Edge Server with access control on and the named queries, and return an admin client."""
        # await self.skip_if_es_not(es.get_admin_client(), ">= 1.1.0")
        await es.write_file(USERS_FILE, USERS.read_text())
        return await es.configure_dataset(db_name="travel", config_file=CONFIG)

    async def _run(self, es: EdgeServerManager, user: str, keyspace: str, name: str) -> list | None:
        """Run named query `name` as `user` through `keyspace` ("db" or "db.scope.collection")."""
        db, _, rest = keyspace.partition(".")
        scope, _, collection = rest.partition(".")
        async with es.get_user_client(get_basic_auth_headers(user, PASSWORD)) as client:
            return await _rows(client.named_query(db, scope, collection, name=name))

    @pytest.mark.asyncio(loop_scope="session")
    async def test_admin_runs_every_named_query(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server with access control on and the named queries")
        admin = await self._start(cblpytest.edge_servers[0])

        self.mark_test_step("Verify the admin can run `airline_ids`, `hotel_ids` and `name_ids`, and each returns rows")
        for db, name in (("travel", "airline_ids"), ("travel", "hotel_ids"), ("names", "name_ids")):
            rows = await _rows(admin.named_query(db, name=name))
            assert rows, f"The admin's `{name}` returned {rows}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_database_level_query_needs_read_on_any_collection(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        es = cblpytest.edge_servers[0]
        self.mark_test_step("Start Edge Server with access control on and the named queries")
        await self._start(es)

        self.mark_test_step("Verify `airline_rw` can run `airline_ids`, and it returns airline IDs")
        rows = await self._run(es, "airline_rw", "travel.travel.airlines", "airline_ids")
        assert rows and all(row["id"].startswith("airline_") for row in rows), f"Unexpected `airline_ids` rows: {rows}"

        self.mark_test_step("Verify `landmark_reader` can run `airline_ids`: it can read a collection in `travel`")
        assert await self._run(es, "landmark_reader", "travel.travel.landmarks", "airline_ids"), (
            "`landmark_reader` was refused a database-level query"
        )

        self.mark_test_step("Verify `wo` (`travel.*`: write) cannot run `airline_ids`: it can read nothing")
        assert await self._run(es, "wo", "travel.travel.airlines", "airline_ids") is None, (
            "A write-only user ran a query"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_collection_restricted_query_needs_read_on_a_listed_collection(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        es = cblpytest.edge_servers[0]
        self.mark_test_step("Start Edge Server with access control on and the named queries")
        await self._start(es)

        self.mark_test_step("Verify `mixed` (reads `travel.hotels`) can run `hotel_ids`, and it returns hotel IDs")
        rows = await self._run(es, "mixed", "travel.travel.hotels", "hotel_ids")
        assert rows and all(row["id"].startswith("hotel_") for row in rows), f"Unexpected `hotel_ids` rows: {rows}"

        self.mark_test_step("Verify `landmark_reader` can run `hotel_ids`: `travel.landmarks` is in its allow list")
        assert await self._run(es, "landmark_reader", "travel.travel.landmarks", "hotel_ids"), (
            "`landmark_reader` was refused a query that lists `travel.landmarks`"
        )

        self.mark_test_step("Verify `airline_rw` cannot run `hotel_ids`: it reads no listed collection")
        assert await self._run(es, "airline_rw", "travel.travel.airlines", "hotel_ids") is None, (
            "`airline_rw` ran a query restricted to `travel.hotels` and `travel.landmarks`"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_no_access_user_runs_no_query(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        es = cblpytest.edge_servers[0]
        self.mark_test_step("Start Edge Server with access control on and the named queries")
        await self._start(es)

        self.mark_test_step("Verify `none` ({}) can run neither `travel` query")
        for name in ("airline_ids", "hotel_ids"):
            assert await self._run(es, "none", "travel.travel.hotels", name) is None, f"`none` ran `{name}`"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_query_access_is_per_database(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        es = cblpytest.edge_servers[0]
        self.mark_test_step("Start Edge Server with access control on and the named queries")
        await self._start(es)

        self.mark_test_step("Verify `names_rw` can run `name_ids` on `names`")
        assert await self._run(es, "names_rw", "names", "name_ids"), "`names_rw` was refused `name_ids`"

        self.mark_test_step("Verify `rw` (`travel.*`) cannot run `name_ids` on `names`")
        assert await self._run(es, "rw", "names", "name_ids") is None, "A `travel` grant ran a query on `names`"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_query_is_checked_against_the_url_keyspace(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        es = cblpytest.edge_servers[0]
        self.mark_test_step("Start Edge Server with access control on and the named queries")
        await self._start(es)

        self.mark_test_step("Verify `landmark_reader` can run `hotel_ids` through `travel.travel.landmarks`")
        assert await self._run(es, "landmark_reader", "travel.travel.landmarks", "hotel_ids"), (
            "`landmark_reader` was refused `hotel_ids` through a keyspace it can read"
        )

        self.mark_test_step("Verify `landmark_reader` is refused `hotel_ids` through `travel`, its default collection")
        assert await self._run(es, "landmark_reader", "travel", "hotel_ids") is None, (
            "`landmark_reader` ran a query through a keyspace it cannot read"
        )
