import asyncio
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblEdgeServerBadResponseError
from cbltest.api.error_types import ErrorDomain
from cbltest.api.replicator import (
    Replicator,
    ReplicatorActivityLevel,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.replicator_types import (
    ReplicatorBasicAuthenticator,
    ReplicatorSessionAuthenticator,
    ReplicatorStatus,
)
from cbltest.responses import ServerVariant

SCRIPT_DIR = str(Path(__file__).parent)

_CONFIG = f"{SCRIPT_DIR}/config/test_cbl_js_session_auth.json"
# Declares `travel` and `names`, so a token minted for one database can be presented to the
# other. Everything else matches _CONFIG, CORS included.
_CONFIG_TWO_DBS = f"{SCRIPT_DIR}/config/test_cbl_js_session_auth_two_dbs.json"

_DB = "travel"
_OTHER_DB = "names"
_SCOPE = "travel"
_COLL = "airlines"
_COLLECTION = f"{_SCOPE}.{_COLL}"
_USER = "admin_user"
_PASSWORD = "password"

# A replicate-role user with no admin bypass, added by the tests that need one.
_LIMITED_USER = "replicate_only"
_LIMITED_PASSWORD = "replicate_pass"

# The design specifies 5 minutes for a one-time token; allow a margin for clock skew.
_ONE_TIME_TTL_SECONDS = 320


def _fmt_error(error: object) -> str:
    """
    Renders an ErrorResponseBody usefully.

    It has no __str__, so interpolating it directly yields a memory address -- which tells
    you a replication failed but not why.
    """
    if error is None:
        return "None"
    return f"{getattr(error, 'domain', '?')}/{getattr(error, 'code', '?')}: {getattr(error, 'message', '')}"


@pytest.mark.min_test_servers(1)
@pytest.mark.min_edge_servers(1)
class TestCblJsEdgeServerSessionAuth(CBLTestClass):
    """
    Session authentication between Couchbase Lite and Edge Server.

    Two things about this suite are worth knowing before reading it.

    First, this appears to be the **first** test in the repository that drives a CBL
    replicator against Edge Server. Every other Edge Server test uses the REST API
    directly, or exercises Edge-to-Edge and Edge-to-Sync-Gateway replication. So a failure
    here may be the CBL-to-Edge path itself rather than anything to do with sessions --
    which is why the suite starts with a Basic-auth control.

    Second, the config is deliberately **not** TLS. Every other platform pins the Edge
    Server certificate, but a browser cannot, and `pinnedServerCert` is declared in the
    JavaScript test server's schema without ever being read. A `wss://` endpoint would
    therefore need `EdgeTestCA` in the browser's own trust store, which is a topology
    concern rather than something these tests should carry. Plain `ws://` keeps the
    variable out.

    The config does carry a `cors` block allowing `http://localhost:5173`. CBL JS runs the
    replicator inside a page, so Edge Server must allow that origin or the `_session` fetch
    fails before any authentication is attempted.

    Per the Edge Server session design (CBL-8630), a session token authenticates the
    `_blipsync` upgrade only -- CBL JS presents it as the subprotocol entry
    `SyncGatewaySession_<token>`. It is not a cookie and not a REST credential, so these
    tests never present it to a REST endpoint; verified against Edge Server 1.2.0, where
    every such presentation returns 401. Revocation therefore goes through Basic auth, as
    the identity of the client that calls it.

    Sessions belong to whichever user a client authenticates as, so `create_session` and
    `delete_session` take no credentials -- the admin client returned by `configure_dataset`
    is already `admin_user`. `create_session` returns the token itself: a one-time session
    is read from `one_time_session_id` and a reusable one from `session_id`, so a token
    coming back at all is the assertion that Edge Server used the expected key.

    The REST-only properties of `_session` are covered by test_session.py. What needs a
    replicator, and lives here, is everything about presenting a token at the `_blipsync`
    upgrade: that it works, that it is scoped, that it carries the right identity, and that
    it fails cleanly when it should not work.
    """

    # ---------------------------------------------------------------- helpers

    async def _assert_auth_rejected(self, cblpytest: CBLPyTest, replicator: Replicator) -> ReplicatorStatus:
        """
        Asserts a replicator stopped because its credentials were rejected.

        CBL JS cannot see an HTTP status for a refused WebSocket upgrade, so a SESSION
        rejection surfaces as `WebSocketError` with code -1 rather than 401. Basic auth
        does produce a readable 401, because it fails on the `_session` fetch first. Both
        are accepted; what matters is that the replicator stopped with an error rather than
        sitting in OFFLINE retrying a credential that will never work.
        """
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is not None, "Replicator stopped without an error; expected a rejection"

        if (await cblpytest.test_servers[0].get_info()).variant == ServerVariant.JS:
            assert status.error.code in (401, -1), f"Expected 401 or -1, got {_fmt_error(status.error)}"
        else:
            assert status.error.code == 10401 and ErrorDomain.equal(status.error.domain, ErrorDomain.CBL), (
                f"Expected CBL/10401, got {_fmt_error(status.error)}"
            )
        return status

    @staticmethod
    def _pull_replicator(
        db,
        edge_server,
        token: str | None = None,
        user: str | None = None,
        password: str = _PASSWORD,
        db_name: str = _DB,
        collection: str = _COLLECTION,
        continuous: bool = False,
    ) -> Replicator:
        """A pull of one collection, authenticated by session token or Basic credentials."""
        authenticator = (
            ReplicatorSessionAuthenticator(token)
            if token is not None
            else ReplicatorBasicAuthenticator(user, password)
        )
        return Replicator(
            db,
            edge_server.replication_url(db_name),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry([collection])],
            authenticator=authenticator,
            continuous=continuous,
        )

    @staticmethod
    async def _add_limited_user(cblpytest: CBLPyTest):
        """
        Add a replicate-role user and return a fresh admin client.

        `add_user` restarts Edge Server, so anything created before this call is gone and the
        previous client predates the restart.
        """
        manager = cblpytest.edge_servers[0]
        await manager.add_user(_LIMITED_USER, _LIMITED_PASSWORD, role="replicate")
        return manager.get_admin_client()

    # ---------------------------------------------------------------- the control

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_basic_auth_control(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Control: CBL replicates against Edge Server with Basic credentials.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Reset local database with an empty `travel.airlines` collection")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[_COLLECTION])

        self.mark_test_step("Start a pull replicator using Basic credentials")
        replicator = self._pull_replicator(dbs[0], edge_server, user=_USER)
        await replicator.start()

        self.mark_test_step("Check replication completes without error")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Basic-auth replication against Edge Server failed: {_fmt_error(status.error)}"

        self.mark_test_step("Check documents actually arrived")
        local = await dbs[0].get_all_documents(_COLLECTION)
        assert len(local[_COLLECTION]) > 0, (
            "Replication reported success but pulled no documents from Edge Server"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_reusable_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        ESS-16: CBL replicates against Edge Server using a reusable session token.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Create a reusable session as the admin user")
        token = await edge_server.create_session(_DB, one_time=False)
        assert token, "Edge Server returned no session token"

        self.mark_test_step("Reset local database with an empty `travel.airlines` collection")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[_COLLECTION])

        self.mark_test_step("""
            Start a replicator
            * endpoint: `/travel`
            * collections: `travel.airlines`
            * type: pull
            * continuous: false
            * credentials: Edge Server session token
        """)
        replicator = self._pull_replicator(dbs[0], edge_server, token=token)
        await replicator.start()

        self.mark_test_step("Check replication completes without error")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Session-authenticated replication failed: {_fmt_error(status.error)}"

        self.mark_test_step("Check documents actually arrived, not just that the replicator succeeded")
        local = await dbs[0].get_all_documents(_COLLECTION)
        remote = await edge_server.get_all_documents(_DB, scope=_SCOPE, collection=_COLL)
        assert len(local[_COLLECTION]) == len(remote.rows), (
            f"Local has {len(local[_COLLECTION])} docs, Edge Server has {len(remote.rows)}"
        )
        assert len(remote.rows) > 0, "Edge Server has no documents; the comparison is vacuous"

        await edge_server.delete_session(_DB)
        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_two_replicators_share_a_reusable_token(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        A reusable token authenticates more than one connection at a time.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Create one reusable session")
        token = await edge_server.create_session(_DB, one_time=False)

        self.mark_test_step("Reset two local databases")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1", "db2"], collections=[_COLLECTION])

        self.mark_test_step("Start two replicators concurrently on the same token")
        first = self._pull_replicator(dbs[0], edge_server, token=token)
        second = self._pull_replicator(dbs[1], edge_server, token=token)
        await asyncio.gather(first.start(), second.start())

        statuses = await asyncio.gather(
            first.wait_for(ReplicatorActivityLevel.STOPPED),
            second.wait_for(ReplicatorActivityLevel.STOPPED),
        )

        self.mark_test_step("Check both replications succeeded on the one token")
        for i, status in enumerate(statuses, start=1):
            assert status.error is None, (
                f"Replicator {i} failed on a shared reusable token: {_fmt_error(status.error)}"
            )

        for i, db in enumerate(dbs, start=1):
            local = await db.get_all_documents(_COLLECTION)
            assert len(local[_COLLECTION]) > 0, f"Replicator {i} pulled nothing"

        await edge_server.delete_session(_DB)
        await cblpytest.test_servers[0].cleanup()


    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_is_scoped_to_its_database(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        A token minted for one database does not authenticate a replication against another.
        Requires a config declaring both databases, and both seeded.
        """
        self.mark_test_step("Configure Edge Server with `travel` and `names`")
        edge_server = await cblpytest.edge_servers[0].configure_datasets(
            (_DB, _OTHER_DB), config_file=_CONFIG_TWO_DBS
        )

        self.mark_test_step(f"Create a reusable session scoped to `{_DB}`")
        token = await edge_server.create_session(_DB, one_time=False)

        self.mark_test_step("Reset a local database")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[_COLLECTION])

        self.mark_test_step(f"Present that token to `{_OTHER_DB}` instead")
        replicator = self._pull_replicator(dbs[0], edge_server, token=token, db_name=_OTHER_DB)
        await replicator.start()

        self.mark_test_step("Check the token is refused for a database it was not minted for")
        await self._assert_auth_rejected(cblpytest, replicator)

        await edge_server.delete_session(_DB)
        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_carries_the_users_permissions(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        A session resolves to a user, so it grants exactly what that user's credentials grant.

        Every other test here authenticates as `admin_user`, whose admin role bypasses
        collection-level checks -- so none of them would notice if a session authenticated as
        "someone, therefore everything". Compares a session-authenticated replication against
        the same user's Basic-authenticated one: whatever the limited user can do with a
        password, they must be able to do with a token, and no more.

        This matters more with per-database access control (CBL-8556) in the picture: a
        session that dropped permissions would be a way around it.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        await cblpytest.edge_servers[0].configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Add a replicate-role user")
        edge_server = await self._add_limited_user(cblpytest)

        self.mark_test_step("Reset two local databases")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1", "db2"], collections=[_COLLECTION])

        self.mark_test_step("Replicate as that user with Basic credentials, to establish the baseline")
        basic = self._pull_replicator(
            dbs[0], edge_server, user=_LIMITED_USER, password=_LIMITED_PASSWORD
        )
        await basic.start()
        basic_status = await basic.wait_for(ReplicatorActivityLevel.STOPPED)
        basic_docs = await dbs[0].get_all_documents(_COLLECTION)

        self.mark_test_step("Replicate as the same user with a session token")
        async with cblpytest.edge_servers[0].get_user_client(_LIMITED_USER, _LIMITED_PASSWORD) as limited:
            token = await limited.create_session(_DB, one_time=False)
        session_repl = self._pull_replicator(dbs[1], edge_server, token=token)
        await session_repl.start()
        session_status = await session_repl.wait_for(ReplicatorActivityLevel.STOPPED)
        session_docs = await dbs[1].get_all_documents(_COLLECTION)

        self.mark_test_step(
            f"Basic: {_fmt_error(basic_status.error)}, {len(basic_docs[_COLLECTION])} docs. "
            f"Session: {_fmt_error(session_status.error)}, {len(session_docs[_COLLECTION])} docs."
        )
        assert (basic_status.error is None) == (session_status.error is None), (
            "A session token and the same user's password produced different outcomes: "
            f"Basic {_fmt_error(basic_status.error)} vs session {_fmt_error(session_status.error)}"
        )
        assert len(session_docs[_COLLECTION]) == len(basic_docs[_COLLECTION]), (
            f"Session auth replicated {len(session_docs[_COLLECTION])} documents where Basic auth for "
            f"the same user replicated {len(basic_docs[_COLLECTION])}; a session must carry the "
            "user's permissions, not bypass them"
        )

        await cblpytest.test_servers[0].cleanup()

    # ---------------------------------------------------------------- rejection

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_invalid_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        ESS-18: a session token that was never issued is rejected cleanly.

        The important half is that the replicator reaches STOPPED. A replicator that sits
        in OFFLINE retrying a token Edge Server will never accept is a worse outcome than
        an outright failure, because nothing surfaces to the application.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Reset local database with an empty `travel.airlines` collection")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[_COLLECTION])

        self.mark_test_step("Start a replicator with a session token that was never issued")
        replicator = self._pull_replicator(
            dbs[0], edge_server, token="bm90YXJlYWxlZGdlc2VydmVyc2Vzc2lvbg"
        )
        await replicator.start()

        self.mark_test_step("Check the replicator stops with a rejection rather than retrying")
        status = await self._assert_auth_rejected(cblpytest, replicator)
        self.mark_test_step(f"Rejected with {_fmt_error(status.error)}")

        self.mark_test_step("Check nothing replicated")
        local = await dbs[0].get_all_documents(_COLLECTION)
        assert len(local[_COLLECTION]) == 0, (
            f"{len(local[_COLLECTION])} documents replicated on an invalid session token"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_revoked_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        ESS-10 + ESS-18: a revoked session is rejected for a subsequent replication.

        Revokes before starting the replicator; mid-flight revocation is a separate question,
        covered by test_revocation_during_replication.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Create a reusable session, then revoke it")
        token = await edge_server.create_session(_DB, one_time=False)
        # DELETE /{db}/_session revokes "the caller's session", and the caller is whoever this
        # client authenticates as. With exactly one outstanding session that is unambiguous;
        # see test_revoke_with_several_sessions_outstanding for the case where it is not.
        await edge_server.delete_session(_DB)

        self.mark_test_step("Reset local database with an empty `travel.airlines` collection")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[_COLLECTION])

        self.mark_test_step("Start a replicator with the revoked session")
        replicator = self._pull_replicator(dbs[0], edge_server, token=token)
        await replicator.start()

        self.mark_test_step("Check the revoked session is rejected")
        await self._assert_auth_rejected(cblpytest, replicator)

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_revoke_with_several_sessions_outstanding(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        Records which session DELETE revokes when a user holds more than one.

        The design says the endpoint revokes "the caller's session", identified by Basic auth,
        and does not say what that means with several outstanding. The plausible answers are
        all of them, the most recent, or the oldest, and they differ for a user signed in on a
        phone and a laptop: logging out of one should not log out the other.

        Asserts nothing about which, only reports what happened -- this exists to produce
        evidence for that design conversation. What it does assert is that revocation did
        something: silently revoking nothing would be worse than any of the three.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Create three reusable sessions for the same user")
        tokens = [await edge_server.create_session(_DB, one_time=False) for _ in range(3)]

        self.mark_test_step("Revoke once")
        await edge_server.delete_session(_DB)

        self.mark_test_step("Try each token in turn and record which still work")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1", "db2", "db3"], collections=[_COLLECTION])
        survived: list[int] = []
        for i, (token, db) in enumerate(zip(tokens, dbs)):
            replicator = self._pull_replicator(db, edge_server, token=token)
            await replicator.start()
            status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
            if status.error is None:
                survived.append(i)

        self.mark_test_step(
            f"Sessions surviving a single revocation, oldest first: {survived} of {list(range(len(tokens)))}"
        )
        assert len(survived) < len(tokens), (
            "A single DELETE /_session revoked nothing: all three tokens still authenticate a "
            "replication. Revocation must invalidate at least the session it claims to."
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_revocation_during_replication(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Records whether revoking a session stops a replication already running on it.

        Sync Gateway does not re-validate a session for an established BLIP connection -- it
        tracks the resolved user, not the session -- so a revoked session keeps syncing until
        the connection drops. That is defensible, but it is an assumption about Edge Server
        until measured, and "logging out does not stop the sync" is a question a security
        review will eventually ask.

        Asserts only the safe half: once the connection is torn down, the revoked token must
        not get it back. Whether the in-flight connection survives is reported, not asserted.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Create a reusable session and start a continuous replicator on it")
        token = await edge_server.create_session(_DB, one_time=False)
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[_COLLECTION])
        replicator = self._pull_replicator(dbs[0], edge_server, token=token, continuous=True)
        await replicator.start()
        await replicator.wait_for(ReplicatorActivityLevel.IDLE)

        self.mark_test_step("Revoke the session while the replicator is connected")
        await edge_server.delete_session(_DB)

        self.mark_test_step("Write a document on Edge Server and see whether it still flows")
        await edge_server.put_document_with_id(
            {"name": "post-revocation"}, "midflight_doc", _DB, scope=_SCOPE, collection=_COLL
        )
        await asyncio.sleep(10)
        local = await dbs[0].get_all_documents(_COLLECTION)
        still_syncing = any(doc.id == "midflight_doc" for doc in local[_COLLECTION])
        self.mark_test_step(
            f"Replication after revocation: still syncing={still_syncing}, "
            f"status={(await replicator.get_status()).activity_level}"
        )

        self.mark_test_step("Stop the replicator and check the revoked token cannot reconnect")
        await replicator.stop()
        await replicator.wait_for(ReplicatorActivityLevel.STOPPED)

        reconnect = self._pull_replicator(dbs[0], edge_server, token=token)
        await reconnect.start()
        await self._assert_auth_rejected(cblpytest, reconnect)

        await cblpytest.test_servers[0].cleanup()

    # ---------------------------------------------------------------- lifecycle

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_lost_on_edge_server_restart(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        ESS-11: Edge Server sessions do not survive a restart, and the client fails cleanly.

        This is the empirical check on "in-memory sessions are sufficient". Sync Gateway
        stores sessions as documents and they persist; Edge Server holds them in memory, so
        a restart should invalidate them. What matters for a client is that it gets a clean
        rejection it can act on, rather than hanging.

        If this test *fails* because the session still works, that is worth knowing too --
        it would mean Edge Server sessions are persisted after all.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        manager = cblpytest.edge_servers[0]
        edge_server = await manager.configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Create a reusable session")
        token = await edge_server.create_session(_DB, one_time=False)

        self.mark_test_step("Restart Edge Server")
        # Restarts are the manager's job, and a client is fixed to the config it was built
        # with, so take a fresh one rather than reusing the pre-restart client.
        await manager.kill_server()
        edge_server = await manager.start_server()

        self.mark_test_step("Reset local database with an empty `travel.airlines` collection")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[_COLLECTION])

        self.mark_test_step("Start a replicator with the pre-restart session")
        replicator = self._pull_replicator(dbs[0], edge_server, token=token)
        await replicator.start()

        self.mark_test_step("Check the stale session is rejected cleanly")
        status = await self._assert_auth_rejected(cblpytest, replicator)
        self.mark_test_step(f"Stale session rejected with {_fmt_error(status.error)}")

        self.mark_test_step("Check a freshly minted session works after the restart")
        fresh = await edge_server.create_session(_DB, one_time=False)
        recovered = self._pull_replicator(dbs[0], edge_server, token=fresh)
        await recovered.start()
        status = await recovered.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Fresh session was also rejected after restart: {_fmt_error(status.error)}"

        await edge_server.delete_session(_DB)
        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_continuous_replication_survives_a_network_drop(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        A continuous replicator on a reusable token recovers when the network comes back.

        This is the case a browser actually hits -- the laptop sleeps, the wifi changes -- and
        it is the only test here that exercises a *reconnect* rather than a first connection.
        A token that authenticates the initial upgrade but not the second would leave a client
        permanently offline after any blip, which nothing else in this suite would catch.

        Uses the firewall rather than a restart, so the server keeps its session table and the
        only thing that changes is reachability.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        manager = cblpytest.edge_servers[0]
        edge_server = await manager.configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Create a reusable session and start a continuous replicator")
        token = await edge_server.create_session(_DB, one_time=False)
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[_COLLECTION])
        replicator = self._pull_replicator(dbs[0], edge_server, token=token, continuous=True)
        await replicator.start()
        await replicator.wait_for(ReplicatorActivityLevel.IDLE)

        try:
            self.mark_test_step("Cut the Edge Server off, then restore it")
            await manager.set_firewall_rules(deny=["0.0.0.0/0"])
            await asyncio.sleep(15)
            await manager.reset_firewall()

            self.mark_test_step("Check the replicator reconnects on the same token")
            await replicator.wait_for(ReplicatorActivityLevel.IDLE)

            self.mark_test_step("Check documents written after the drop still arrive")
            await edge_server.put_document_with_id(
                {"name": "post-reconnect"}, "reconnect_doc", _DB, scope=_SCOPE, collection=_COLL
            )
            await asyncio.sleep(10)
            local = await dbs[0].get_all_documents(_COLLECTION)
            assert any(doc.id == "reconnect_doc" for doc in local[_COLLECTION]), (
                "The replicator did not resume after the network was restored; a reusable token "
                "must authenticate a reconnect as well as the first connection"
            )
        finally:
            # A leftover DROP rule hides the host from every later test.
            await manager.reset_firewall()
            await replicator.stop()
            await cblpytest.test_servers[0].cleanup()

    @pytest.mark.slow
    @pytest.mark.asyncio(loop_scope="session")
    async def test_one_time_session_expires(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        A one-time token stops working after its TTL, even if never presented.

        The only observable path to expiry: Edge Server 1.2.0 reports no `expires` field and
        exposes no TTL override, so the choice is wall-clock or nothing. Marked slow -- it
        sleeps for the full five minutes and belongs in the nightly run, not the PR pipeline.

        An unused token that never expires would mean a token leaked from a browser's console
        or a log stays valid indefinitely, which is the risk the short TTL exists to bound.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Create a one-time session and leave it unused")
        token = await edge_server.create_session(_DB, one_time=True)

        self.mark_test_step(f"Wait {_ONE_TIME_TTL_SECONDS}s for the 5 minute TTL to pass")
        await asyncio.sleep(_ONE_TIME_TTL_SECONDS)

        self.mark_test_step("Reset local database with an empty `travel.airlines` collection")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[_COLLECTION])

        self.mark_test_step("Present the expired token")
        replicator = self._pull_replicator(dbs[0], edge_server, token=token)
        await replicator.start()

        self.mark_test_step("Check the expired token is rejected")
        await self._assert_auth_rejected(cblpytest, replicator)

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_one_time_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        ESS-19: what happens when a replicator authenticates with a one-time token.

        This records behaviour rather than asserting a specific outcome, because the Edge
        Server design does not say what a client should present when a connection using a
        one-time token drops and reconnects -- the token is already consumed. That may be a
        genuine design gap, and this test exists to produce the evidence for that
        conversation rather than to pass or fail on a guess.

        The one assertion made is the safe one: a one-time token must not be reusable for a
        second, independent replication.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Create a one-time session")
        # Returning at all means Edge Server answered with one_time_session_id; a reusable
        # response would raise KeyError in the client rather than yielding a token.
        token = await edge_server.create_session(_DB, one_time=True)
        assert token, "Edge Server returned no one-time session token"

        self.mark_test_step("Reset local databases with an empty `travel.airlines` collection")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1", "db2"], collections=[_COLLECTION])

        self.mark_test_step("Start a first replicator with the one-time token")
        first = self._pull_replicator(dbs[0], edge_server, token=token)
        await first.start()
        first_status = await first.wait_for(ReplicatorActivityLevel.STOPPED)
        self.mark_test_step(f"First replication ended with error: {_fmt_error(first_status.error)}")

        self.mark_test_step("Start a second replicator reusing the same one-time token")
        second = self._pull_replicator(dbs[1], edge_server, token=token)
        await second.start()
        second_status = await second.wait_for(ReplicatorActivityLevel.STOPPED)
        self.mark_test_step(f"Second replication ended with error: {_fmt_error(second_status.error)}")

        second_docs = await dbs[1].get_all_documents(_COLLECTION)
        assert second_status.error is not None or len(second_docs[_COLLECTION]) == 0, (
            "A one-time session token was accepted for a second, independent replication. "
            "Either the token was not consumed on first use, or one-time semantics are not "
            "enforced on the replication path."
        )

        await cblpytest.test_servers[0].cleanup()