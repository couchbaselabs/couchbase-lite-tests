import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from pathlib import Path
from typing import Any, Protocol

import pytest
import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cluster import CouchbaseCluster
from cbltest.api.edgeservermanager import EdgeServerManager
from cbltest.api.error import CblRemoteBadResponseError

SCRIPT_DIR = str(Path(__file__).parent)

_ES_CONFIG = f"{SCRIPT_DIR}/config/test_session.json"
_DB = "names"


class _SessionClient(Protocol):
    """The session calls that EdgeServer and SyncGatewayUserClient share."""

    async def create_session(self, db_name: str, one_time: bool = True) -> str: ...

    async def get_session(self, db_name: str) -> dict: ...

    async def delete_session(self, db_name: str) -> None: ...


class _Backend(ABC):
    """The server whose `_session` endpoint is under test, so every test runs against each one."""

    primary_user: str
    anonymous_get_allowed: bool
    repeat_delete_allowed: bool

    @abstractmethod
    async def configure(self) -> _SessionClient:
        """Load the `names` dataset and return a client for `primary_user`."""

    @abstractmethod
    async def add_user(self, name: str, password: str) -> _SessionClient:
        """Add a non-admin user and return a client for `primary_user`, which can be a new one."""

    @abstractmethod
    def user_client(self, name: str, password: str) -> AbstractAsyncContextManager[_SessionClient]: ...

    @abstractmethod
    def anonymous_client(self) -> AbstractAsyncContextManager[_SessionClient]: ...


class _EdgeServerBackend(_Backend):
    primary_user = "admin_user"
    anonymous_get_allowed = False
    repeat_delete_allowed = False

    def __init__(self, manager: EdgeServerManager) -> None:
        self.__manager = manager

    async def configure(self) -> _SessionClient:
        return await self.__manager.configure_dataset(db_name=_DB, config_file=_ES_CONFIG)

    async def add_user(self, name: str, password: str) -> _SessionClient:
        # add_user restarts Edge Server, so the existing clients are stale
        await self.__manager.add_user(name, password, role="replicate")
        return self.__manager.get_admin_client()

    def user_client(self, name: str, password: str) -> AbstractAsyncContextManager[_SessionClient]:
        return self.__manager.get_user_client(name, password)

    def anonymous_client(self) -> AbstractAsyncContextManager[_SessionClient]:
        return self.__manager.get_anonymous_client()


class _SyncGatewayBackend(_Backend):
    primary_user = "user1"
    anonymous_get_allowed = True
    repeat_delete_allowed = True
    _PRIMARY_PASSWORD = "pass"

    def __init__(self, cluster: CouchbaseCluster, dataset_path: Path, stack: AsyncExitStack) -> None:
        self.__cluster = cluster
        self.__dataset_path = dataset_path
        self.__stack = stack
        self.__primary: _SessionClient | None = None

    async def configure(self) -> _SessionClient:
        await self.__cluster.configure_dataset(self.__dataset_path, _DB)
        sg = self.__cluster.sync_gateways[0]
        self.__primary = await self.__stack.enter_async_context(
            sg.get_user_client(self.primary_user, self._PRIMARY_PASSWORD)
        )
        return self.__primary

    async def add_user(self, name: str, password: str) -> _SessionClient:
        assert self.__primary is not None, "configure() must run before add_user()"
        await self.__cluster.sync_gateways[0].add_user(_DB, name, password)
        return self.__primary

    def user_client(self, name: str, password: str) -> AbstractAsyncContextManager[_SessionClient]:
        return self.__cluster.sync_gateways[0].get_user_client(name, password)

    def anonymous_client(self) -> AbstractAsyncContextManager[_SessionClient]:
        return self.__cluster.sync_gateways[0].get_anonymous_client()


@pytest_asyncio.fixture(
    loop_scope="session",
    params=[
        pytest.param("edge_server", marks=pytest.mark.min_edge_servers(1)),
        pytest.param("sync_gateway", marks=[pytest.mark.sgw, pytest.mark.min_sync_gateways(1)]),
    ],
)
async def backend(request: pytest.FixtureRequest, cblpytest: CBLPyTest, dataset_path: Path) -> AsyncIterator[_Backend]:
    if request.param == "edge_server":
        yield _EdgeServerBackend(cblpytest.edge_servers[0])
        return

    async with AsyncExitStack() as stack:
        yield _SyncGatewayBackend(cblpytest.clusters[0], dataset_path, stack)


class TestSession(CBLTestClass):
    @staticmethod
    async def _call(client: _SessionClient, verb: str, db: str) -> Any:
        """Dispatch to one of the three session verbs, so a test can parametrize over them."""
        if verb == "create":
            return await client.create_session(db, one_time=False)
        if verb == "get":
            return await client.get_session(db)
        return await client.delete_session(db)

    @staticmethod
    def _client_for(backend: _Backend, credentials: str) -> AbstractAsyncContextManager[_SessionClient]:
        """A client for one credential case; anonymous means no Authorization header at all."""
        if credentials == "anonymous":
            return backend.anonymous_client()
        if credentials == "wrong password":
            return backend.user_client(backend.primary_user, "not-the-password")
        return backend.user_client("nosuchuser", "password")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_create_session_both_modes(self, backend: _Backend) -> None:
        self.mark_test_step("Configure the backend with the `names` dataset")
        client = await backend.configure()

        self.mark_test_step("Create a one-time session, then a reusable one")
        one_time = await client.create_session(_DB, one_time=True)
        reusable = await client.create_session(_DB, one_time=False)

        self.mark_test_step("Check both tokens are usable strings and differ from each other")
        for label, token in (("one-time", one_time), ("reusable", reusable)):
            assert isinstance(token, str), f"{label}: expected a token string, got {type(token).__name__}"
            assert token and token.strip() == token, f"{label}: empty or padded token {token!r}"
        assert one_time != reusable, "The one-time and reusable sessions got the same token"
        await client.delete_session(_DB)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_tokens_are_unique(self, backend: _Backend) -> None:
        self.mark_test_step("Configure the backend with the `names` dataset")
        client = await backend.configure()

        self.mark_test_step("Create 3 sessions one after another")
        sequential = [await client.create_session(_DB, one_time=False) for _ in range(3)]

        self.mark_test_step("Create 10 more concurrently")
        concurrent = await asyncio.gather(*(client.create_session(_DB, one_time=False) for _ in range(10)))

        self.mark_test_step("Check all 13 tokens are non-empty and distinct")
        tokens = sequential + list(concurrent)
        assert all(tokens), "At least one creation returned an empty token"
        collisions = len(tokens) - len(set(tokens))
        assert collisions == 0, (
            f"{collisions} duplicate token(s) across {len(sequential)} sequential and "
            f"{len(concurrent)} concurrent creations"
        )

        await client.delete_session(_DB)

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("verb", ["create", "get", "delete"])
    @pytest.mark.parametrize("credentials", ["wrong password", "unknown user", "anonymous"])
    async def test_session_endpoints_reject_bad_credentials(
        self, backend: _Backend, verb: str, credentials: str
    ) -> None:
        self.mark_test_step("Configure the backend with the `names` dataset")
        await backend.configure()

        self.mark_test_step(f"Attempt to {verb} a session with {credentials}")
        async with self._client_for(backend, credentials) as client:
            if credentials == "anonymous" and verb == "get" and backend.anonymous_get_allowed:
                info = await client.get_session(_DB)
                assert info.get("userCtx", {}).get("name") is None, f"Anonymous GET /_session reported a user: {info}"
                return

            with pytest.raises(CblRemoteBadResponseError) as excinfo:
                await self._call(client, verb, _DB)

        assert excinfo.value.code == 401, f"{verb} with {credentials}: expected 401, got {excinfo.value.code}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_non_admin_can_create_own_session(self, backend: _Backend) -> None:
        self.mark_test_step("Configure the backend with the `names` dataset")
        await backend.configure()

        self.mark_test_step("Add a non-admin user")
        await backend.add_user("session_user", "session_pass")

        self.mark_test_step("Create a session as that user")
        async with backend.user_client("session_user", "session_pass") as client:
            token = await client.create_session(_DB, one_time=False)
            assert token, "A non-admin user could not create a session for themselves"
            await client.delete_session(_DB)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delete_already_deleted_session(self, backend: _Backend) -> None:
        self.mark_test_step("Configure the backend with the `names` dataset")
        client = await backend.configure()

        self.mark_test_step("Create a reusable session, then delete it")
        await client.create_session(_DB, one_time=False)
        await client.delete_session(_DB)

        self.mark_test_step("Delete the same session again")
        if backend.repeat_delete_allowed:
            await client.delete_session(_DB)
        else:
            with pytest.raises(CblRemoteBadResponseError) as excinfo:
                await client.delete_session(_DB)
            assert excinfo.value.code == 404, f"Repeat delete: expected 404, got {excinfo.value.code}"

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("verb", ["create", "get", "delete"])
    async def test_session_endpoints_reject_unknown_database(self, backend: _Backend, verb: str) -> None:
        self.mark_test_step("Configure the backend with the `names` dataset")
        client = await backend.configure()

        self.mark_test_step(f"Attempt to {verb} a session against `nosuchdb`")
        with pytest.raises(CblRemoteBadResponseError) as excinfo:
            await self._call(client, verb, "nosuchdb")

        assert excinfo.value.code in (401, 403, 404), (
            f"{verb}: expected a client error for an unknown database, got {excinfo.value.code}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_session_reports_authenticated_caller(self, backend: _Backend) -> None:
        self.mark_test_step("Configure the backend with the `names` dataset")
        await backend.configure()

        self.mark_test_step("Add a second user, then give both users a session")
        primary = await backend.add_user("other_user", "other_pass")
        await primary.create_session(_DB, one_time=False)

        async with backend.user_client("other_user", "other_pass") as other:
            await other.create_session(_DB, one_time=False)

            self.mark_test_step("Ask GET /_session as each user in turn")
            primary_info = await primary.get_session(_DB)
            other_info = await other.get_session(_DB)

            self.mark_test_step(f"Responses: primary={primary_info}, other={other_info}")
            for expected_user, info in ((backend.primary_user, primary_info), ("other_user", other_info)):
                assert info.get("ok") is True, f"{expected_user}: GET /_session did not report ok, got {info}"
                assert info.get("userCtx", {}).get("name") == expected_user, (
                    f"GET /_session as `{expected_user}` reported {info.get('userCtx')}"
                )

            await other.delete_session(_DB)
        await primary.delete_session(_DB)
