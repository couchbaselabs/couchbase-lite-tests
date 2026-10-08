import re
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.error import CblEdgeServerBadResponseError
from cbltest.api.syncgateway import get_basic_auth_headers

SCRIPT_DIR = Path(__file__).parent
CONFIG = str(SCRIPT_DIR / "config" / "test_session.json")
USERS = SCRIPT_DIR / "config" / "test_session_users.json"
USERS_FILE = "/home/ec2-user/user/session_users.json"
PASSWORD = "password"
SESSION_ID = re.compile(r"^[0-9a-fA-F]{32}$")


@pytest.mark.min_edge_servers(1)
class TestEdgeServerSession(CBLTestClass):
    async def _setup(self, cblpytest: CBLPyTest) -> EdgeServer:
        """Start Edge Server on the session config with the session users, and return an admin client."""
        es = cblpytest.edge_servers[0]
        await es.write_file(USERS_FILE, USERS.read_text())
        return await es.configure_dataset(db_name="travel", config_file=CONFIG)

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "one_time", [None, False, "", "0", "random"], ids=["missing", "false", "empty", "zero", "garbage"]
    )
    async def test_create_session_requires_one_time_true(
        self, cblpytest: CBLPyTest, dataset_path: Path, one_time: bool | str | None
    ) -> None:
        self.mark_test_step("Start Edge Server on the session config with the test users")
        admin = await self._setup(cblpytest)

        self.mark_test_step("Verify POST /travel/_session with the case's one_time is rejected with 400")
        with pytest.raises(CblEdgeServerBadResponseError) as e:
            await admin.create_session("travel", one_time=one_time)
        assert e.value.code == 400, f"one_time={one_time!r}: expected 400, got {e.value.code}"

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "headers",
        [get_basic_auth_headers("rw", "not-the-password"), get_basic_auth_headers("nosuchuser", PASSWORD), {}],
        ids=["wrong_password", "unknown_user", "anonymous"],
    )
    async def test_create_session_rejects_bad_credentials(
        self, cblpytest: CBLPyTest, dataset_path: Path, headers: dict[str, str]
    ) -> None:
        self.mark_test_step("Start Edge Server on the session config with the test users")
        await self._setup(cblpytest)

        self.mark_test_step(
            "Verify POST /travel/_session?one_time=true with the case's credentials is rejected with 401"
        )
        async with cblpytest.edge_servers[0].get_user_client(headers) as client:
            with pytest.raises(CblEdgeServerBadResponseError) as e:
                await client.create_session("travel")
        assert e.value.code == 401, f"Expected 401, got {e.value.code}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_create_session_unknown_database(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Start Edge Server on the session config with the test users")
        admin = await self._setup(cblpytest)

        self.mark_test_step("Verify POST /nosuchdb/_session?one_time=true as admin is rejected with 404")
        with pytest.raises(CblEdgeServerBadResponseError) as e:
            await admin.create_session("nosuchdb")
        assert e.value.code == 404, f"Expected 404 for an unknown database, got {e.value.code}"

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "user, db, expected",
        [
            ("rw", "travel", 200),
            ("ro", "travel", 200),
            ("coll", "travel", 200),
            ("other_db", "names", 200),
            ("wo", "travel", 200),
            ("none", "travel", 403),
            ("other_db", "travel", 403),
            ("rw", "names", 403),
        ],
        ids=[
            "read_write",
            "read_only",
            "one_readable_collection",
            "own_database",
            "write_only",
            "no_access",
            "other_database",
            "unlisted_database",
        ],
    )
    async def test_create_session_access_control(
        self, cblpytest: CBLPyTest, dataset_path: Path, user: str, db: str, expected: int
    ) -> None:
        self.mark_test_step("Start Edge Server on the session config with the test users")
        await self._setup(cblpytest)

        self.mark_test_step("Verify POST /{db}/_session?one_time=true as the user issues a session, or is rejected")
        async with cblpytest.edge_servers[0].get_user_client(get_basic_auth_headers(user, PASSWORD)) as client:
            if expected == 200:
                body = await client.create_session(db)
                assert SESSION_ID.match(body["one_time_session_id"]), f"`{user}` on `{db}`: no session ID in {body}"
            else:
                with pytest.raises(CblEdgeServerBadResponseError) as e:
                    await client.create_session(db)
                assert e.value.code == expected, f"`{user}` on `{db}`: expected {expected}, got {e.value.code}"