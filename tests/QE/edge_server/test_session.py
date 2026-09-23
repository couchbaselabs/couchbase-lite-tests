import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.edgeservermanager import EdgeServerManager
from cbltest.api.error import CblEdgeServerBadResponseError

SCRIPT_DIR = str(Path(__file__).parent)

_CONFIG = f"{SCRIPT_DIR}/config/test_session.json"
_DB = "names"
_ADMIN = "admin_user"
_ADMIN_PASSWORD = "password"


@pytest.mark.min_edge_servers(1)
class TestEdgeServerSession(CBLTestClass):
    @staticmethod
    def _manager(cblpytest: CBLPyTest) -> EdgeServerManager:
        """The manager, which owns user administration and restarts; the client only speaks REST."""
        return cblpytest.edge_servers[0]

    async def _configure(self, cblpytest: CBLPyTest) -> EdgeServer:
        return await self._manager(cblpytest).configure_dataset(db_name=_DB, config_file=_CONFIG)

    async def _add_user(self, cblpytest: CBLPyTest, name: str, password: str, role: str = "replicate") -> EdgeServer:
        """Add a user and return a fresh client, since add_user restarts Edge Server."""
        manager = self._manager(cblpytest)
        await manager.add_user(name, password, role=role)
        return manager.get_admin_client()

    @staticmethod
    async def _call(client: EdgeServer, verb: str, db: str) -> Any:
        """Dispatch to one of the three session verbs, so a test can parametrize over them."""
        if verb == "create":
            return await client.create_session(db, one_time=False)
        if verb == "get":
            return await client.get_session(db)
        return await client.delete_session(db)

    @asynccontextmanager
    async def _client_for(self, cblpytest: CBLPyTest, credentials: str) -> AsyncIterator[EdgeServer]:
        """A client for one credential case; anonymous means no Authorization header at all."""
        manager = self._manager(cblpytest)
        if credentials == "anonymous":
            async with manager.get_anonymous_client() as client:
                yield client
        elif credentials == "wrong password":
            async with manager.get_user_client(_ADMIN, "not-the-password") as client:
                yield client
        else:
            async with manager.get_user_client("nosuchuser", "password") as client:
                yield client

    @pytest.mark.asyncio(loop_scope="session")
    async def test_create_session_both_modes(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Create a one-time session, then a reusable one")
        one_time = await edge_server.create_session(_DB, one_time=True)
        reusable = await edge_server.create_session(_DB, one_time=False)

        self.mark_test_step("Check both tokens are usable strings and differ from each other")
        for label, token in (("one-time", one_time), ("reusable", reusable)):
            assert isinstance(token, str), f"{label}: expected a token string, got {type(token).__name__}"
            assert token and token.strip() == token, f"{label}: empty or padded token {token!r}"
        await edge_server.delete_session(_DB)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_tokens_are_unique(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Create 3 sessions one after another")
        sequential = [await edge_server.create_session(_DB, one_time=False) for _ in range(3)]

        self.mark_test_step("Create 10 more concurrently")
        concurrent = await asyncio.gather(*(edge_server.create_session(_DB, one_time=False) for _ in range(10)))

        self.mark_test_step("Check all 13 tokens are non-empty and distinct")
        tokens = sequential + list(concurrent)
        assert all(tokens), "At least one creation returned an empty token"
        collisions = len(tokens) - len(set(tokens))
        assert collisions == 0, (
            f"{collisions} duplicate token(s) across {len(sequential)} sequential and "
            f"{len(concurrent)} concurrent creations"
        )

        await edge_server.delete_session(_DB)

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("verb", ["create", "get", "delete"])
    @pytest.mark.parametrize("credentials", ["wrong password", "unknown user", "anonymous"])
    async def test_session_endpoints_reject_bad_credentials(
        self, cblpytest: CBLPyTest, dataset_path: Path, verb: str, credentials: str
    ) -> None:
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        await self._configure(cblpytest)

        self.mark_test_step(f"Attempt to {verb} a session with {credentials}")

        async with self._client_for(cblpytest, credentials) as client:
            with pytest.raises(CblEdgeServerBadResponseError) as excinfo:
                await self._call(client, verb, _DB)

        assert excinfo.value.code == 401, f"{verb} with {credentials}: expected 401, got {excinfo.value.code}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_non_admin_can_create_own_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        await self._configure(cblpytest)

        self.mark_test_step("Add a non-admin user")
        await self._add_user(cblpytest, "session_user", "session_pass")

        self.mark_test_step("Create a session as that user")
        async with self._manager(cblpytest).get_user_client("session_user", "session_pass") as client:
            token = await client.create_session(_DB, one_time=False)
            assert token, "A non-admin user could not create a session for themselves"
            await client.delete_session(_DB)

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("verb", ["create", "get", "delete"])
    async def test_session_endpoints_reject_unknown_database(
        self, cblpytest: CBLPyTest, dataset_path: Path, verb: str
    ) -> None:
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step(f"Attempt to {verb} a session against `nosuchdb`")
        with pytest.raises(CblEdgeServerBadResponseError) as excinfo:
            await self._call(edge_server, verb, "nosuchdb")

        assert excinfo.value.code in (401, 403, 404), (
            f"{verb}: expected a client error for an unknown database, got {excinfo.value.code}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_session_reports_authenticated_caller(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        await self._configure(cblpytest)

        self.mark_test_step("Add a second user, then give both users a session")
        edge_server = await self._add_user(cblpytest, "other_user", "other_pass")
        await edge_server.create_session(_DB, one_time=False)

        async with self._manager(cblpytest).get_user_client("other_user", "other_pass") as other:
            await other.create_session(_DB, one_time=False)

            self.mark_test_step("Ask GET /_session as each user in turn")
            admin_info = await edge_server.get_session(_DB)
            other_info = await other.get_session(_DB)

            self.mark_test_step(f"Responses: admin={admin_info}, other={other_info}")
            for expected_user, info in ((_ADMIN, admin_info), ("other_user", other_info)):
                assert info.get("ok") is True, f"{expected_user}: GET /_session did not report ok, got {info}"
                assert info.get("userCtx", {}).get("name") == expected_user, (
                    f"GET /_session as `{expected_user}` reported {info.get('userCtx')}"
                )

            await other.delete_session(_DB)
        await edge_server.delete_session(_DB)
