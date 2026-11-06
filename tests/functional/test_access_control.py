import json
from collections.abc import Awaitable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from aiohttp import ClientConnectorError
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.edgeservermanager import EdgeServerManager
from cbltest.api.error import CblEdgeServerBadResponseError, CblTimeoutError
from cbltest.api.syncgateway import get_basic_auth_headers

SCRIPT_DIR = Path(__file__).parent
CONFIG = SCRIPT_DIR / "config" / "test_access_control.json"
USERS = SCRIPT_DIR / "config" / "test_access_control_users.json"
USERS_FILE = "/home/ec2-user/user/access_control_users.json"
EDGE_LOG = "/home/ec2-user/log/edge.log"
PASSWORD = "password"


async def _status(request: Awaitable[Any]) -> int:
    """The HTTP status a REST request was answered with, reporting any success as 200."""
    try:
        await request
        return 200
    except CblEdgeServerBadResponseError as e:
        return e.code


async def _allowed(request: Awaitable[Any]) -> bool:
    """Whether a REST request succeeds.  A 403 is a denial; any other failure is a test error."""
    status = await _status(request)
    assert status in (200, 403), f"Expected success or 403, got {status}"
    return status == 200


async def _check(client: EdgeServer, who: str, keyspace: str, *, read: bool, write: bool) -> None:
    """Assert whether `client` can read (`_all_docs`) and write (`PUT`) `keyspace` ("db" or "db.scope.collection")."""
    db, _, rest = keyspace.partition(".")
    scope, _, collection = rest.partition(".")
    can_read = await _allowed(client.get_all_documents(db, scope, collection))
    can_write = await _allowed(client.put_document_with_id({"by": who}, f"{who}_{uuid4().hex}", db, scope, collection))
    assert (can_read, can_write) == (read, write), (
        f"{who} on {keyspace}: (read, write) expected {(read, write)}, got {(can_read, can_write)}"
    )


@pytest.mark.min_edge_servers(1)
class TestAccessControl(CBLTestClass):
    async def _start(self, es: EdgeServerManager, config: str | Path = CONFIG) -> EdgeServer:
        """Start Edge Server on `config` with the access-control users, and return an admin client."""
        # await self.skip_if_es_not(es.get_admin_client(), ">= 1.1.0")
        await es.write_file(USERS_FILE, USERS.read_text())
        return await es.configure_dataset(db_name="travel", config_file=str(config))

    def _client(self, es: EdgeServerManager, user: str) -> AbstractAsyncContextManager[EdgeServer]:
        """A client signed in as `user`."""
        return es.get_user_client(get_basic_auth_headers(user, PASSWORD))

    @pytest.mark.asyncio(loop_scope="session")
    async def test_access_blocks_require_the_flag(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        es = cblpytest.edge_servers[0]
        config = json.loads(CONFIG.read_text())
        config["enable_user_access_control"] = False
        flag_off = tmp_path / "access_control_off.json"
        flag_off.write_text(json.dumps(config))

        self.mark_test_step("Start Edge Server with access control off and users that have access blocks")
        with pytest.raises((CblEdgeServerBadResponseError, ClientConnectorError, CblTimeoutError)) as e:
            await self._start(es, flag_off)

        self.mark_test_step("Verify startup fails, saying access control must be enabled")
        log = await es.get_admin_client().download_log_file(EDGE_LOG, tmp_path / "edge.log")
        output = getattr(e.value, "body", "") + log.read_text(errors="replace")
        assert "requires setting 'enable_user_access_control: true'" in output, f"Unexpected startup failure:\n{output}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_no_access_user_is_denied_everywhere(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        es = cblpytest.edge_servers[0]
        self.mark_test_step("Start Edge Server with access control on")
        await self._start(es)

        async with self._client(es, "none") as client:
            self.mark_test_step("Verify `none` ({}) can neither read nor write any keyspace")
            for keyspace in ("travel", "travel.travel.hotels", "names"):
                await _check(client, "none", keyspace, read=False, write=False)

            self.mark_test_step("Verify /_all_dbs lists no databases for `none`")
            assert await client.get_all_dbs() == [], "A user with no access was shown databases"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_admin_has_full_access(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        es = cblpytest.edge_servers[0]
        self.mark_test_step("Start Edge Server with access control on")
        admin = await self._start(es)

        self.mark_test_step("Verify the admin can read and write every keyspace")
        for keyspace in ("travel", "travel.travel.hotels", "travel.travel.airlines", "names"):
            await _check(admin, "admin_user", keyspace, read=True, write=True)

        self.mark_test_step("Verify /_all_dbs lists both databases for the admin")
        assert {"travel", "names"} <= set(await admin.get_all_dbs()), "The admin was not shown every database"

        self.mark_test_step("Verify the admin can call /_active_tasks and /_replicate")
        assert isinstance(await admin.get_active_tasks(), list), "The admin could not call /_active_tasks"
        assert isinstance(await admin.all_replication_status(), list), "The admin could not call /_replicate"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_admin_access_block_is_ignored(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        es = cblpytest.edge_servers[0]
        self.mark_test_step("Start Edge Server with access control on")
        await self._start(es)

        self.mark_test_step("Verify `admin_with_access` (admin role, `names`: read) can read and write `travel`")
        async with self._client(es, "admin_with_access") as client:
            await _check(client, "admin_with_access", "travel.travel.hotels", read=True, write=True)
            await _check(client, "admin_with_access", "names", read=True, write=True)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_admin_endpoints_need_a_role(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        es = cblpytest.edge_servers[0]
        self.mark_test_step("Start Edge Server with access control on")
        await self._start(es)

        async with self._client(es, "replicator") as client:
            self.mark_test_step("Verify `replicator` (replicate role, {}) can call /_replicate but not /_active_tasks")
            assert await _allowed(client.all_replication_status()), "The replicate role could not call /_replicate"
            assert not await _allowed(client.get_active_tasks()), "The replicate role called /_active_tasks"

            self.mark_test_step("Verify `replicator` cannot read or write `travel`")
            await _check(client, "replicator", "travel.travel.hotels", read=False, write=False)

        self.mark_test_step("Verify `rw` (full data access, no role) cannot call /_replicate or /_active_tasks")
        async with self._client(es, "rw") as client:
            assert not await _allowed(client.all_replication_status()), "A user with no role called /_replicate"
            assert not await _allowed(client.get_active_tasks()), "A user with no role called /_active_tasks"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_keyspace_patterns(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        es = cblpytest.edge_servers[0]
        self.mark_test_step("Start Edge Server with access control on")
        await self._start(es)

        self.mark_test_step("Verify `travel.*` covers the default collection and every scope")
        async with self._client(es, "rw") as client:
            await _check(client, "rw", "travel", read=True, write=True)
            await _check(client, "rw", "travel.travel.hotels", read=True, write=True)

        self.mark_test_step("Verify `travel.travel.*` covers the `travel` scope but not the default collection")
        async with self._client(es, "scope_reader") as client:
            await _check(client, "scope_reader", "travel.travel.hotels", read=True, write=False)
            await _check(client, "scope_reader", "travel.travel.airlines", read=True, write=False)
            await _check(client, "scope_reader", "travel", read=False, write=False)

        self.mark_test_step("Verify `travel` covers only the default collection")
        async with self._client(es, "default_reader") as client:
            await _check(client, "default_reader", "travel", read=True, write=False)
            await _check(client, "default_reader", "travel.travel.hotels", read=False, write=False)

        self.mark_test_step("Verify `travel.travel.hotels` covers only that collection")
        async with self._client(es, "mixed") as client:
            await _check(client, "mixed", "travel.travel.hotels", read=True, write=True)
            await _check(client, "mixed", "travel.travel.airlines", read=True, write=False)
            await _check(client, "mixed", "travel.travel.landmarks", read=False, write=False)

        self.mark_test_step("Verify a grant on `names` gives nothing on `travel`")
        async with self._client(es, "names_rw") as client:
            await _check(client, "names_rw", "names", read=True, write=True)
            await _check(client, "names_rw", "travel", read=False, write=False)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_missing_keyspace_is_403_without_access(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        es = cblpytest.edge_servers[0]
        self.mark_test_step("Start Edge Server with access control on")
        await self._start(es)

        async with self._client(es, "names_rw") as client:
            self.mark_test_step(
                "Verify `names_rw` gets 403 for a missing collection in `travel`, as for one that exists"
            )
            missing = await _status(client.get_all_documents("travel", "travel", "nosuchcollection"))
            existing = await _status(client.get_all_documents("travel", "travel", "hotels"))
            assert missing == existing == 403, (
                f"Missing collection {missing}, existing collection {existing}: existence leaks"
            )

            self.mark_test_step("Verify `names_rw` gets 403 for a database the server does not serve")
            status = await _status(client.get_all_documents("nosuchdb"))
            assert status == 403, f"A missing database returned {status}, which reveals that it does not exist"
