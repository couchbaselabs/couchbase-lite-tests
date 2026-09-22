import asyncio
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

    async def _add_user(
        self, cblpytest: CBLPyTest, name: str, password: str, role: str = "replicate"
    ) -> EdgeServer:
        """Add a user and return a fresh client, since add_user restarts Edge Server."""
        manager = self._manager(cblpytest)
        await manager.add_user(name, password, role=role)
        return manager.get_admin_client()

    @staticmethod
    async def _call(edge_server: EdgeServer, verb: str, db: str, username: str, password: str) -> Any:
        """Dispatch to one of the three session verbs, so a test can parametrize over them."""
        if verb == "create":
            return await edge_server.create_session(db, username, password, one_time=False)
        if verb == "get":
            return await edge_server.get_session(db, username, password)
        return await edge_server.delete_session(db, username, password)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_create_session_both_modes(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Create a one-time session, then a reusable one")
        one_time = await edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=True)
        reusable = await edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=False)

        self.mark_test_step("Check both tokens are usable strings and differ from each other")
        for label, token in (("one-time", one_time), ("reusable", reusable)):
            assert isinstance(token, str), f"{label}: expected a token string, got {type(token).__name__}"
            assert token and token.strip() == token, f"{label}: empty or padded token {token!r}"
        assert one_time != reusable, "Both modes returned the same token; the one_time flag looks ignored"
        await edge_server.delete_session(_DB, _ADMIN, _ADMIN_PASSWORD)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_tokens_are_unique(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Create 3 sessions one after another")
        sequential = [
            await edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=False) for _ in range(3)
        ]

        self.mark_test_step("Create 10 more concurrently")
        concurrent = await asyncio.gather(
            *(edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=False) for _ in range(10))
        )

        self.mark_test_step("Check all 13 tokens are non-empty and distinct")
        tokens = sequential + list(concurrent)
        assert all(tokens), "At least one creation returned an empty token"
        collisions = len(tokens) - len(set(tokens))
        assert collisions == 0, (
            f"{collisions} duplicate token(s) across {len(sequential)} sequential and "
            f"{len(concurrent)} concurrent creations"
        )

        await edge_server.delete_session(_DB, _ADMIN, _ADMIN_PASSWORD)

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("verb", ["create", "get", "delete"])
    @pytest.mark.parametrize(
        ("label", "username", "password"),
        [
            ("wrong password", _ADMIN, "not-the-password"),
            ("unknown user", "nosuchuser", "password"),
            ("no credentials", "", ""),
        ],
    )
    async def test_session_endpoints_reject_bad_credentials(
        self, cblpytest: CBLPyTest, dataset_path: Path, verb: str, label: str, username: str, password: str
    ) -> None:
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step(f"Attempt to {verb} a session with {label}")
        with pytest.raises(CblEdgeServerBadResponseError) as excinfo:
            await self._call(edge_server, verb, _DB, username, password)

        assert excinfo.value.code == 401, f"{verb} with {label}: expected 401, got {excinfo.value.code}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_non_admin_can_create_own_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        await self._configure(cblpytest)

        self.mark_test_step("Add a non-admin user")
        edge_server = await self._add_user(cblpytest, "session_user", "session_pass")

        self.mark_test_step("Create a session as that user")
        token = await edge_server.create_session(_DB, "session_user", "session_pass", one_time=False)
        assert token, "A non-admin user could not create a session for themselves"

        await edge_server.delete_session(_DB, "session_user", "session_pass")

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("verb", ["create", "get", "delete"])
    async def test_session_endpoints_reject_unknown_database(
        self, cblpytest: CBLPyTest, dataset_path: Path, verb: str
    ) -> None:
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step(f"Attempt to {verb} a session against `nosuchdb`")
        try:
            await self._call(edge_server, verb, "nosuchdb", _ADMIN, _ADMIN_PASSWORD)
        except CblEdgeServerBadResponseError as e:
            assert e.code in (401, 403, 404), f"Expected a client error for an unknown database, got {e.code}"
        else:
            assert verb == "delete", f"{verb} succeeded against a database that does not exist"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_session_reports_authenticated_caller(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        await self._configure(cblpytest)

        self.mark_test_step("Add a second user, then give both users a session")
        edge_server = await self._add_user(cblpytest, "other_user", "other_pass")
        await edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=False)
        await edge_server.create_session(_DB, "other_user", "other_pass", one_time=False)

        self.mark_test_step("Ask GET /_session as each user in turn")
        admin_info = await edge_server.get_session(_DB, _ADMIN, _ADMIN_PASSWORD)
        other_info = await edge_server.get_session(_DB, "other_user", "other_pass")

        self.mark_test_step(f"Responses: admin={admin_info}, other={other_info}")
        for expected_user, info in ((_ADMIN, admin_info), ("other_user", other_info)):
            assert info.get("ok") is True, f"{expected_user}: GET /_session did not report ok, got {info}"
            assert info.get("userCtx", {}).get("name") == expected_user, (
                f"GET /_session as `{expected_user}` reported {info.get('userCtx')}"
            )

        await edge_server.delete_session(_DB, _ADMIN, _ADMIN_PASSWORD)
        await edge_server.delete_session(_DB, "other_user", "other_pass")