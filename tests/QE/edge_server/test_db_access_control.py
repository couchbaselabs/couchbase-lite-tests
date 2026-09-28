from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.edgeservermanager import EdgeServerManager
from cbltest.api.error import CblEdgeServerBadResponseError, CblTestError

SCRIPT_DIR = Path(__file__).parent
CONFIG_DIR = SCRIPT_DIR / "config"

_USERS_HOST_PATH = "/opt/couchbase-edge-server/etc/users_access_control.json"
_USERS_FILE = CONFIG_DIR / "users_access_control.json"

_ENFORCING_BY_DEFAULT = f"{CONFIG_DIR}/config_per_db_access_control.json"
_OPT_IN = f"{CONFIG_DIR}/config_access_control_opt_in.json"
_UNSET_DATABASE = f"{CONFIG_DIR}/config_access_control_unset_database.json"

_DBS = ("names", "travel", "posts")

_ADMIN = ("admin_user", "password")
_READER = ("reader", "password")
_WRITER = ("writer", "password")
_NOACCESS = ("noaccess", "password")


@pytest.mark.min_edge_servers(1)
class TestPerDatabaseAccessControl(CBLTestClass):
    @staticmethod
    def _manager(cblpytest: CBLPyTest) -> EdgeServerManager:
        return cblpytest.edge_servers[0]

    async def _start(self, cblpytest: CBLPyTest, config_file: str) -> EdgeServer:
        """Seed all three databases and start Edge Server on `config_file`."""
        manager = self._manager(cblpytest)
        await manager.write_file(_USERS_HOST_PATH, _USERS_FILE.read_text())
        return await manager.configure_datasets(_DBS, config_file)

    @asynccontextmanager
    async def _as(self, cblpytest: CBLPyTest, user: tuple[str, str]) -> AsyncIterator[EdgeServer]:
        async with self._manager(cblpytest).get_user_client(*user) as client:
            yield client

    @staticmethod
    async def _status(client: EdgeServer, db_name: str) -> int:
        """The status of `GET /{db}`, with a success reported as 200."""
        try:
            await client.get_db_info(db_name)
        except CblEdgeServerBadResponseError as e:
            return e.code
        return 200

    @staticmethod
    async def _read_status(client: EdgeServer, keyspace: str) -> int:
        """The status of `GET /{keyspace}/_all_docs`, with a success reported as 200."""
        db_name, _, collection = keyspace.partition(".")
        try:
            await client.get_all_documents(db_name, collection=collection)
        except CblEdgeServerBadResponseError as e:
            return e.code
        return 200

    @staticmethod
    async def _write_status(client: EdgeServer, db_name: str, doc_id: str) -> int:
        """The status of writing a document, with a success reported as 200."""
        try:
            await client.put_document_with_id({"x": 1}, doc_id, db_name)
        except CblEdgeServerBadResponseError as e:
            return e.code
        return 200

    # ---------------------------------------------------------------- the open database

    @pytest.mark.asyncio(loop_scope="session")
    async def test_open_database_ignores_rules(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        With the flag off, rules are never consulted -- they neither grant nor deny.

        `writer` holds travel:[write] only and `reader` holds travel:[read] only, so on an
        enforcing database each would be refused the other operation. On an open one both
        succeed, which is the behaviour the design turns on.
        """
        self.mark_test_step("Start Edge Server with root access control on and `travel` exempt")
        await self._start(cblpytest, _ENFORCING_BY_DEFAULT)

        self.mark_test_step("A write-only user can read from the open database")
        async with self._as(cblpytest, _WRITER) as writer:
            assert await self._read_status(writer, "travel") == 200

        self.mark_test_step("A read-only user can write to the open database")
        async with self._as(cblpytest, _READER) as reader:
            assert await self._write_status(reader, "travel", "perdb_rw") == 200

    @pytest.mark.asyncio(loop_scope="session")
    async def test_empty_access_block_has_full_access_when_open(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        A user with ``access: {}`` has zero rules, which is 403 everywhere in 1.1.

        On an open database the rules are not consulted at all, so the same user has full read
        and write. This is the case that separates "no rules match" from "rules not evaluated".
        """
        self.mark_test_step("Start Edge Server with root access control on and `travel` exempt")
        await self._start(cblpytest, _ENFORCING_BY_DEFAULT)

        self.mark_test_step("The zero-rule user can read and write the open database")
        async with self._as(cblpytest, _NOACCESS) as noaccess:
            assert await self._read_status(noaccess, "travel") == 200
            assert await self._write_status(noaccess, "travel", "perdb_noaccess") == 200

    @pytest.mark.asyncio(loop_scope="session")
    async def test_unknown_collection_on_open_database_is_404(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        An open database has no keyspaces to hide, so a missing collection is 404, not 403.

        Existence masking is a consequence of enforcement. Returning 403 here would leak the
        fact that the database is being access-controlled when it is not.
        """
        self.mark_test_step("Start Edge Server with root access control on and `travel` exempt")
        await self._start(cblpytest, _ENFORCING_BY_DEFAULT)

        self.mark_test_step("Read a collection that does not exist on the open database")
        async with self._as(cblpytest, _NOACCESS) as noaccess:
            assert await self._read_status(noaccess, "travel.nosuchcollection") == 404

    # ---------------------------------------------------------------- enforcing databases

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("db_name", ["names", "posts"])
    async def test_enforcing_databases_unaffected(
        self, cblpytest: CBLPyTest, dataset_path: Path, db_name: str
    ) -> None:
        """
        Databases that resolve to enforcing behave as they did in 1.1, in the same server.

        `names` inherits the root flag and `posts` restates it, so both must refuse a user
        with no rule for them while the exempt database alongside stays open.
        """
        self.mark_test_step("Start Edge Server with root access control on and `travel` exempt")
        await self._start(cblpytest, _ENFORCING_BY_DEFAULT)

        self.mark_test_step(f"A user with no rule for `{db_name}` is refused")
        async with self._as(cblpytest, _WRITER) as writer:
            assert await self._status(writer, db_name) == 403

        self.mark_test_step(f"The zero-rule user is refused `{db_name}`")
        async with self._as(cblpytest, _NOACCESS) as noaccess:
            assert await self._status(noaccess, db_name) == 403

    @pytest.mark.asyncio(loop_scope="session")
    async def test_rules_are_still_enforced(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """A matching rule still grants on an enforcing database, and admin still bypasses."""
        self.mark_test_step("Start Edge Server with root access control on and `travel` exempt")
        await self._start(cblpytest, _ENFORCING_BY_DEFAULT)

        self.mark_test_step("A user with names:[read] can read `names`")
        async with self._as(cblpytest, _READER) as reader:
            assert await self._status(reader, "names") == 200

        self.mark_test_step("Admin reaches every database")
        async with self._as(cblpytest, _ADMIN) as admin:
            for db_name in _DBS:
                assert await self._status(admin, db_name) == 200, f"admin was refused `{db_name}`"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_unknown_collection_on_enforcing_database_is_403(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """Existence masking still applies where the flag resolves to enforcing."""
        self.mark_test_step("Start Edge Server with root access control on and `travel` exempt")
        await self._start(cblpytest, _ENFORCING_BY_DEFAULT)

        self.mark_test_step("Read a collection that does not exist on an enforcing database")
        async with self._as(cblpytest, _WRITER) as writer:
            assert await self._read_status(writer, "names.nosuchcollection") == 403

    # ---------------------------------------------------------------- isolation

    @pytest.mark.asyncio(loop_scope="session")
    async def test_open_access_does_not_leak_into_enforcing_database(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Full access to an open database grants nothing on an enforcing one.

        This is the risk the per-database flag introduces: one exempt database must not become
        a way in to the rest of the server.
        """
        self.mark_test_step("Start Edge Server with root access control on and `travel` exempt")
        await self._start(cblpytest, _ENFORCING_BY_DEFAULT)

        self.mark_test_step("The zero-rule user has the open database but not the enforcing ones")
        async with self._as(cblpytest, _NOACCESS) as noaccess:
            assert await self._status(noaccess, "travel") == 200
            assert await self._status(noaccess, "names") == 403
            assert await self._status(noaccess, "posts") == 403

        self.mark_test_step("A rule for one enforcing database grants nothing on another")
        async with self._as(cblpytest, _READER) as reader:
            assert await self._status(reader, "names") == 200
            assert await self._status(reader, "posts") == 403

    @pytest.mark.asyncio(loop_scope="session")
    async def test_unserved_database_is_masked(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        A keyspace naming a database the server does not serve must be masked, not 404.

        There is no per-database config to consult for it, so the answer has to fall back to
        the server-wide one. A 404 would make database existence probeable, and would be a
        regression introduced by per-database scoping rather than a pre-existing gap.
        """
        self.mark_test_step("Start Edge Server with root access control on and `travel` exempt")
        await self._start(cblpytest, _ENFORCING_BY_DEFAULT)

        self.mark_test_step("An unserved database is indistinguishable from a forbidden one")
        async with self._as(cblpytest, _WRITER) as writer:
            unserved = await self._read_status(writer, "nosuchdb.anything")
            forbidden = await self._read_status(writer, "names.nosuchcollection")

        assert unserved == 403, f"Unserved database returned {unserved}; existence leaks"
        assert unserved == forbidden, (
            f"Unserved database returned {unserved} while a forbidden keyspace returned "
            f"{forbidden}; the two must be indistinguishable"
        )

    # ---------------------------------------------------------------- _all_dbs

    @pytest.mark.asyncio(loop_scope="session")
    async def test_all_dbs_lists_open_databases_for_everyone(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        `_all_dbs` filtering follows the same resolution, per database.

        An open database is listed for every authenticated user, including one with zero
        rules, while enforcing databases stay filtered.
        """
        self.mark_test_step("Start Edge Server with root access control on and `travel` exempt")
        await self._start(cblpytest, _ENFORCING_BY_DEFAULT)

        self.mark_test_step("The zero-rule user sees only the open database")
        async with self._as(cblpytest, _NOACCESS) as noaccess:
            dbs = set(await noaccess.get_all_dbs())
        assert "travel" in dbs, f"Open database missing from _all_dbs: {dbs}"
        assert {"names", "posts"}.isdisjoint(dbs), f"Enforcing databases leaked into _all_dbs: {dbs}"

        self.mark_test_step("A user with a rule sees that database as well as the open one")
        async with self._as(cblpytest, _READER) as reader:
            dbs = set(await reader.get_all_dbs())
        assert {"names", "travel"} <= dbs, f"Expected names and travel, got {dbs}"

        self.mark_test_step("Admin sees all three")
        async with self._as(cblpytest, _ADMIN) as admin:
            dbs = set(await admin.get_all_dbs())
        assert set(_DBS) <= dbs, f"Admin should see every database, got {dbs}"

    # ---------------------------------------------------------------- no root key

    @pytest.mark.asyncio(loop_scope="session")
    async def test_opt_in_config_enforces_only_where_asked(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        With no root key the default is false, so only databases that opt in are enforced.

        `posts` has no setting anywhere, which is the row that would silently start enforcing
        if the default were ever taken as true. An unenforced database must behave exactly as
        it did in 1.0: every configured user has unrestricted access.
        """
        self.mark_test_step("Start Edge Server on the opt-in config, with no root-level key")
        await self._start(cblpytest, _OPT_IN)

        self.mark_test_step("The database that opted in is enforcing")
        async with self._as(cblpytest, _NOACCESS) as noaccess:
            assert await self._status(noaccess, "names") == 403

            self.mark_test_step("The database with no setting anywhere is open")
            assert await self._status(noaccess, "posts") == 200
            assert await self._write_status(noaccess, "posts", "optin_absent") == 200

            self.mark_test_step("The database that opted out explicitly is open")
            assert await self._status(noaccess, "travel") == 200

    # ---------------------------------------------------------------- startup validation

    @pytest.mark.asyncio(loop_scope="session")
    async def test_rules_for_unset_database_fail_startup(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        A rule naming a served database with no setting anywhere must refuse to start.

        The database would otherwise be open while its users carry rules for it, which fails
        open silently -- the rules read as a restriction that is not applied. An explicit
        false is the way to say the database is meant to be open.
        """
        self.mark_test_step("Write the users file, which carries rules for `names`")
        manager = self._manager(cblpytest)
        await manager.write_file(_USERS_HOST_PATH, _USERS_FILE.read_text())

        self.mark_test_step("Start on a config where `names` sets no flag and there is no root key")
        with pytest.raises((CblEdgeServerBadResponseError, CblTestError)):
            await manager.configure_datasets(_DBS, _UNSET_DATABASE)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_rules_for_exempt_database_start_normally(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        A rule for a database that sets the flag to false is a deliberate exemption.

        It warns rather than failing, because unlike the unset case the intent is explicit.
        The rules are ignored, which is what the open-database tests above assert; this one
        only pins that the server starts and serves.
        """
        self.mark_test_step("Start Edge Server with `travel` exempt and user rules naming it")
        edge_server = await self._start(cblpytest, _ENFORCING_BY_DEFAULT)

        self.mark_test_step("The server came up and serves the exempt database")
        assert await self._status(edge_server, "travel") == 200