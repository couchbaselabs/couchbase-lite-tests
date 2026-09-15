import asyncio
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.error import CblEdgeServerBadResponseError

SCRIPT_DIR = str(Path(__file__).parent)

_CONFIG = f"{SCRIPT_DIR}/config/test_session.json"
_DB = "names"
_ADMIN = "admin_user"
_ADMIN_PASSWORD = "password"


@pytest.mark.min_edge_servers(1)
class TestEdgeServerSessionEndpoint(CBLTestClass):
    """
    Functional tests for Edge Server's ``_session`` endpoint, driven entirely over REST.

    **Scope, and why it is narrower than it looks.** An Edge Server session token is not a
    general-purpose credential. Per CBL-8630 it is validated in exactly one place -- the
    ``_blipsync`` WebSocket upgrade, where CBL JS presents it as the subprotocol entry
    ``SyncGatewaySession_<token>``. Verified against Edge Server 1.2.0: presenting a valid
    token to a REST endpoint as a cookie, as a bearer header, or as a query parameter all
    return 401.

    So this suite covers what REST can actually observe -- who may create a session, what
    the response contains, and revocation -- and deliberately does not attempt to validate
    a token, because there is no REST path that would. Token *use* is covered by
    test_cbl_js_session_auth.py, which needs a CBL test server and a browser.

    Deliberately carries no ``min_test_servers`` marker: everything here is REST, so it
    runs on any topology with an Edge Server and gives fast feedback on the endpoint
    without a browser in the loop.

    Not covered here, with reasons:

    * One-time consumption, reusability, and database scoping of a token -- all require
      presenting it, which only ``_blipsync`` accepts.
    * Expiry (the design specifies 5 minutes for one-time and 24 hours for reusable).
      Edge Server 1.2.0 returns no ``expires`` field, and no TTL override was found, so
      these are either wall-clock-expensive or unobservable from a client.
    * The background expiry sweep, which has no externally visible signal.
    """

    async def _configure(self, cblpytest: CBLPyTest) -> EdgeServer:
        return await cblpytest.edge_servers[0].configure_dataset(db_name=_DB, config_file=_CONFIG)

    # ---------------------------------------------------------------- creation

    @pytest.mark.asyncio(loop_scope="session")
    async def test_create_reusable_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """ESS-02: an authenticated user can create a reusable session for themselves."""
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Create a reusable session")
        session = await edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=False)

        self.mark_test_step("Check a non-empty token was returned and it is not marked one-time")
        assert session.session_id, "Edge Server returned no session token"
        assert not session.one_time, "Requested a reusable session but it came back marked one-time"

        await edge_server.delete_session(_DB, _ADMIN, _ADMIN_PASSWORD)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_create_one_time_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        ESS-01: an authenticated user can create a one-time session.

        The design says a one-time session is returned under ``one_time_session_id`` while a
        reusable one uses ``session_id``. The client normalises both, so this checks a token
        arrives and records which shape Edge Server actually used -- worth logging, because
        CBL JS 1.0.2 reads only ``one_time_session_id`` and a change here would break it.
        """
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Create a one-time session")
        session = await edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=True)

        self.mark_test_step(f"Token received (one_time={session.one_time}, expires={session.expires})")
        assert session.session_id, "Edge Server returned no one-time session token"
        assert session.one_time, "Requested a one-time session but it came back marked reusable"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sessions_are_distinct(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        ESS-07: separate creation calls yield separate tokens.

        A server that returned the same token twice would make one-time semantics
        meaningless and would let a revoked session be resurrected by asking again.
        """
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Create three reusable sessions for the same user")
        tokens = [
            (await edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=False)).session_id
            for _ in range(3)
        ]

        self.mark_test_step("Check all three tokens are different")
        assert len(set(tokens)) == 3, f"Edge Server reused a session token across separate creations: {tokens}"

        await edge_server.delete_session(_DB, _ADMIN, _ADMIN_PASSWORD)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_concurrent_session_creation(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Creating many sessions at once yields distinct tokens and no errors.

        This is the closest a REST-only test gets to exercising SessionManager's
        thread-safety. Duplicate tokens or a 500 here would point at unsynchronised access
        to the in-memory session map.
        """
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Create 10 sessions concurrently")
        sessions = await asyncio.gather(
            *(edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=False) for _ in range(10))
        )

        self.mark_test_step("Check every token is distinct")
        tokens = [s.session_id for s in sessions]
        assert all(tokens), "At least one concurrent creation returned an empty token"
        assert len(set(tokens)) == len(tokens), (
            f"Concurrent creation produced duplicate tokens ({len(tokens) - len(set(tokens))} collisions)"
        )

        await edge_server.delete_session(_DB, _ADMIN, _ADMIN_PASSWORD)

    # ---------------------------------------------------------------- authorization to create

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        ("label", "username", "password"),
        [
            ("wrong password", _ADMIN, "not-the-password"),
            # 401 and not 404: a different status for an unknown user would let a caller
            # enumerate accounts.
            ("unknown user", "nosuchuser", "password"),
            ("no credentials", "", ""),
        ],
    )
    async def test_create_session_rejects_bad_credentials(
        self, cblpytest: CBLPyTest, dataset_path: Path, label: str, username: str, password: str
    ) -> None:
        """ESS-03/12: creating a session requires valid credentials for the named user."""
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step(f"Attempt to create a session with {label}")
        with pytest.raises(CblEdgeServerBadResponseError) as excinfo:
            await edge_server.create_session(_DB, username, password, one_time=False)

        assert excinfo.value.code == 401, f"{label}: expected 401, got {excinfo.value.code}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_non_admin_can_create_own_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        ESS-03: a non-admin user can create a session for themselves.

        Per the design, "any authenticated user creates their own session" -- creating one
        is not an administrative action. If this required admin rights, a browser client
        could never log itself in, which is the whole point of the endpoint.
        """
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Add a non-admin user")
        await edge_server.add_user("session_user", "session_pass", role="user")

        self.mark_test_step("Create a session as that user")
        edge_server = await self._configure(cblpytest)
        session = await edge_server.create_session(_DB, "session_user", "session_pass", one_time=False)

        assert session.session_id, "A non-admin user could not create a session for themselves"

        await edge_server.delete_session(_DB, "session_user", "session_pass")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_create_session_on_unknown_database(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Creating a session against a database that does not exist is rejected.

        Sessions are scoped to a database in the design, so the database must be resolved
        before a token is minted. A 200 here would mean tokens can be issued for keyspaces
        that do not exist.
        """
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Attempt to create a session against `nosuchdb`")
        with pytest.raises(CblEdgeServerBadResponseError) as excinfo:
            await edge_server.create_session("nosuchdb", _ADMIN, _ADMIN_PASSWORD, one_time=False)

        self.mark_test_step(f"Rejected with {excinfo.value.code}")
        assert excinfo.value.code in (401, 403, 404), (
            f"Expected a client error for an unknown database, got {excinfo.value.code}"
        )

    # ---------------------------------------------------------------- revocation

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delete_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        ESS-10: a user can revoke their own session.

        Note the endpoint identifies the caller by Basic auth, not by presenting the token
        -- the token is not a REST credential. That also means this test cannot confirm the
        token stopped working, only that the revocation was accepted; the replication suite
        covers the effect.
        """
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Create a session, then revoke it")
        session = await edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=False)
        assert session.session_id

        await edge_server.delete_session(_DB, _ADMIN, _ADMIN_PASSWORD)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delete_session_is_idempotent(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Revoking twice, or with nothing outstanding, is not an error.

        Teardown in other suites relies on this: a session may already have been consumed,
        expired, or lost to a restart by the time cleanup runs, and that should not fail a
        test that otherwise passed.
        """
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Revoke with no session outstanding")
        await edge_server.delete_session(_DB, _ADMIN, _ADMIN_PASSWORD)

        self.mark_test_step("Create a session and revoke it twice")
        await edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=False)
        await edge_server.delete_session(_DB, _ADMIN, _ADMIN_PASSWORD)
        await edge_server.delete_session(_DB, _ADMIN, _ADMIN_PASSWORD)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delete_session_requires_credentials(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Revocation cannot be performed anonymously.

        Otherwise any unauthenticated caller could log out an arbitrary user by guessing
        nothing at all -- the endpoint takes no token, so the caller's identity is the only
        thing deciding whose session is destroyed.
        """
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Create a session as the admin user")
        await edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=False)

        self.mark_test_step("Attempt to revoke it with no credentials")
        with pytest.raises(CblEdgeServerBadResponseError) as excinfo:
            await edge_server.delete_session(_DB, "", "")

        assert excinfo.value.code == 401, f"Expected 401 for anonymous revocation, got {excinfo.value.code}"

        await edge_server.delete_session(_DB, _ADMIN, _ADMIN_PASSWORD)

    # ---------------------------------------------------------------- the token is not a REST credential

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        ("label", "header_name", "header_template"),
        [
            ("session cookie", "Cookie", "SyncGatewaySession={token}"),
            ("bearer header", "Authorization", "Bearer {token}"),
        ],
    )
    async def test_token_is_not_a_rest_credential(
        self,
        cblpytest: CBLPyTest,
        dataset_path: Path,
        label: str,
        header_name: str,
        header_template: str,
    ) -> None:
        """
        A valid session token is rejected by REST endpoints.

        This pins down behaviour that is easy to misread as a bug -- it cost real debugging
        time before CBL-8630 made it explicit. Sessions authenticate the `_blipsync` upgrade
        only; there is no REST path that accepts one. Encoding it here means the next person
        finds an assertion rather than an afternoon of curl.

        If this test ever starts failing because a token *is* accepted, that is a
        behavioural change worth knowing about, not a broken test.
        """
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Create a valid reusable session")
        session = await edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=False)

        self.mark_test_step(f"Present the token to `/{_DB}/_all_docs` as a {label}")
        async with edge_server._create_session(
            edge_server.scheme, edge_server.hostname, 59840, None
        ) as anonymous_client:
            anonymous_client.headers[header_name] = header_template.format(token=session.session_id)
            with pytest.raises(CblEdgeServerBadResponseError) as excinfo:
                await edge_server._send_request("get", f"/{_DB}/_all_docs", session=anonymous_client)

        self.mark_test_step(f"Rejected with {excinfo.value.code}")
        assert excinfo.value.code == 401, (
            f"A session token presented as a {label} returned {excinfo.value.code} rather than 401. "
            "Sessions are documented as authenticating the _blipsync upgrade only; if REST now "
            "accepts them, the client and these tests need revisiting."
        )

        await edge_server.delete_session(_DB, _ADMIN, _ADMIN_PASSWORD)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_response_shape(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Records what Edge Server actually returns from ``POST /{db}/_session``.

        Observed on 1.2.0: ``{"ok": true, "session_id": "..."}`` -- no ``cookie_name`` and no
        ``expires``, unlike Sync Gateway. That absence is why EdgeServerSession carries no
        cookie name, and why client-side expiry tests are not possible. Asserting the token
        and recording the rest keeps the test useful without pinning fields that may
        legitimately be added later.
        """
        self.mark_test_step("Configure Edge Server with the `names` dataset")
        edge_server = await self._configure(cblpytest)

        self.mark_test_step("Create a reusable session and inspect what came back")
        session = await edge_server.create_session(_DB, _ADMIN, _ADMIN_PASSWORD, one_time=False)

        assert session.session_id, "No session token in the response"
        self.mark_test_step(
            f"session_id present; expires={session.expires} "
            f"(Edge Server 1.2.0 returns no expires field, so this is expected to be None)"
        )

        await edge_server.delete_session(_DB, _ADMIN, _ADMIN_PASSWORD)
