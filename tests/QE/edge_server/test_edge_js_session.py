from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
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
_USER = "admin_user"
_PASSWORD = "password"


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
    every such presentation returns 401. Revocation therefore goes through Basic auth.
    """

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

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_basic_auth_control(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Control: CBL replicates against Edge Server with Basic credentials.

        Not a session test. It exists so that a failure in the session tests can be
        attributed: if this fails too, the CBL-to-Edge path or the CORS config is broken and
        the session results mean nothing. If this passes and the session tests fail, the
        problem is genuinely session auth.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name="travel", config_file=_CONFIG)

        self.mark_test_step("Reset local database with an empty `travel.airlines` collection")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=["travel.airlines"])

        self.mark_test_step("Start a pull replicator using Basic credentials")
        replicator = Replicator(
            dbs[0],
            edge_server.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorBasicAuthenticator(_USER, _PASSWORD),
        )
        await replicator.start()

        self.mark_test_step("Check replication completes without error")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Basic-auth replication against Edge Server failed: {_fmt_error(status.error)}"

        self.mark_test_step("Check documents actually arrived")
        local = await dbs[0].get_all_documents("travel.airlines")
        assert len(local["travel.airlines"]) > 0, (
            "Replication reported success but pulled no documents from Edge Server"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_reusable_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        ESS-16: CBL replicates against Edge Server using a reusable session token.

        Uses `one_time=False` deliberately. A one-time token is consumed on first
        validation, and a replicator that reconnects would have nothing to present -- see
        test_replicate_with_one_time_session for that case.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name="travel", config_file=_CONFIG)

        self.mark_test_step("Create a reusable session")
        session = await edge_server.create_session("travel", _USER, _PASSWORD, one_time=False)
        assert session.session_id, "Edge Server returned no session token"
        self.mark_test_step(f"Session issued (one_time={session.one_time})")

        self.mark_test_step("Reset local database with an empty `travel.airlines` collection")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=["travel.airlines"])

        self.mark_test_step("""
            Start a replicator
            * endpoint: `/travel`
            * collections: `travel.airlines`
            * type: pull
            * continuous: false
            * credentials: Edge Server session token
        """)
        replicator = Replicator(
            dbs[0],
            edge_server.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorSessionAuthenticator(session.session_id),
        )
        await replicator.start()

        self.mark_test_step("Check replication completes without error")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Session-authenticated replication failed: {_fmt_error(status.error)}"

        self.mark_test_step("Check documents actually arrived, not just that the replicator succeeded")
        local = await dbs[0].get_all_documents("travel.airlines")
        remote = await edge_server.get_all_documents("travel", collection="travel.airlines")
        assert len(local["travel.airlines"]) == len(remote.rows), (
            f"Local has {len(local['travel.airlines'])} docs, Edge Server has {len(remote.rows)}"
        )
        assert len(remote.rows) > 0, "Edge Server has no documents; the comparison is vacuous"

        await edge_server.delete_session("travel", _USER, _PASSWORD)
        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_invalid_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        ESS-18: a session token that was never issued is rejected cleanly.

        The important half is that the replicator reaches STOPPED. A replicator that sits
        in OFFLINE retrying a token Edge Server will never accept is a worse outcome than
        an outright failure, because nothing surfaces to the application.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name="travel", config_file=_CONFIG)

        self.mark_test_step("Reset local database with an empty `travel.airlines` collection")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=["travel.airlines"])

        self.mark_test_step("Start a replicator with a session token that was never issued")
        replicator = Replicator(
            dbs[0],
            edge_server.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorSessionAuthenticator("bm90YXJlYWxlZGdlc2VydmVyc2Vzc2lvbg"),
        )
        await replicator.start()

        self.mark_test_step("Check the replicator stops with a rejection rather than retrying")
        status = await self._assert_auth_rejected(cblpytest, replicator)
        self.mark_test_step(f"Rejected with {_fmt_error(status.error)}")

        self.mark_test_step("Check nothing replicated")
        local = await dbs[0].get_all_documents("travel.airlines")
        assert len(local["travel.airlines"]) == 0, (
            f"{len(local['travel.airlines'])} documents replicated on an invalid session token"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_revoked_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        ESS-10 + ESS-18: a revoked session is rejected for a subsequent replication.

        Revokes before starting the replicator rather than during it. Sync Gateway does not
        re-validate a session for an established BLIP connection (by design -- it tracks the
        user object, not the session), so mid-flight revocation is a separate question and
        not one this test tries to answer for Edge Server.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name="travel", config_file=_CONFIG)

        self.mark_test_step("Create a reusable session, then revoke it")
        session = await edge_server.create_session("travel", _USER, _PASSWORD, one_time=False)
        # DELETE /{db}/_session revokes "the caller's session" as identified by Basic auth.
        # With exactly one outstanding session for this user that is unambiguous; if the
        # user held several, which one is revoked is not specified by the design.
        await edge_server.delete_session("travel", _USER, _PASSWORD)

        self.mark_test_step("Reset local database with an empty `travel.airlines` collection")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=["travel.airlines"])

        self.mark_test_step("Start a replicator with the revoked session")
        replicator = Replicator(
            dbs[0],
            edge_server.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorSessionAuthenticator(session.session_id),
        )
        await replicator.start()

        self.mark_test_step("Check the revoked session is rejected")
        await self._assert_auth_rejected(cblpytest, replicator)

        await cblpytest.test_servers[0].cleanup()

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
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name="travel", config_file=_CONFIG)

        self.mark_test_step("Create a reusable session")
        session = await edge_server.create_session("travel", _USER, _PASSWORD, one_time=False)

        self.mark_test_step("Restart Edge Server")
        await edge_server.kill_server()
        await edge_server.start_server()

        self.mark_test_step("Reset local database with an empty `travel.airlines` collection")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=["travel.airlines"])

        self.mark_test_step("Start a replicator with the pre-restart session")
        replicator = Replicator(
            dbs[0],
            edge_server.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorSessionAuthenticator(session.session_id),
        )
        await replicator.start()

        self.mark_test_step("Check the stale session is rejected cleanly")
        status = await self._assert_auth_rejected(cblpytest, replicator)
        self.mark_test_step(f"Stale session rejected with {_fmt_error(status.error)}")

        self.mark_test_step("Check a freshly minted session works after the restart")
        fresh = await edge_server.create_session("travel", _USER, _PASSWORD, one_time=False)
        recovered = Replicator(
            dbs[0],
            edge_server.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorSessionAuthenticator(fresh.session_id),
        )
        await recovered.start()
        status = await recovered.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Fresh session was also rejected after restart: {_fmt_error(status.error)}"

        await edge_server.delete_session("travel", _USER, _PASSWORD)
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
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name="travel", config_file=_CONFIG)

        self.mark_test_step("Create a one-time session")
        session = await edge_server.create_session("travel", _USER, _PASSWORD, one_time=True)
        assert session.one_time, "Requested a one-time session but the client did not record it as one"

        self.mark_test_step("Reset local database with an empty `travel.airlines` collection")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1", "db2"], collections=["travel.airlines"])

        self.mark_test_step("Start a first replicator with the one-time token")
        first = Replicator(
            dbs[0],
            edge_server.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorSessionAuthenticator(session.session_id),
        )
        await first.start()
        first_status = await first.wait_for(ReplicatorActivityLevel.STOPPED)
        self.mark_test_step(f"First replication ended with error: {_fmt_error(first_status.error)}")

        self.mark_test_step("Start a second replicator reusing the same one-time token")
        second = Replicator(
            dbs[1],
            edge_server.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorSessionAuthenticator(session.session_id),
        )
        await second.start()
        second_status = await second.wait_for(ReplicatorActivityLevel.STOPPED)
        self.mark_test_step(f"Second replication ended with error: {_fmt_error(second_status.error)}")

        second_docs = await dbs[1].get_all_documents("travel.airlines")
        assert second_status.error is not None or len(second_docs["travel.airlines"]) == 0, (
            "A one-time session token was accepted for a second, independent replication. "
            "Either the token was not consumed on first use, or one-time semantics are not "
            "enforced on the replication path."
        )

        await cblpytest.test_servers[0].cleanup()
