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
    """
    if error is None:
        return "None"
    return f"{getattr(error, 'domain', '?')}/{getattr(error, 'code', '?')}: {getattr(error, 'message', '')}"


@pytest.mark.min_test_servers(1)
@pytest.mark.min_edge_servers(1)
class TestCblJsEdgeServerSessionAuth(CBLTestClass):
    async def _assert_auth_rejected(self, cblpytest: CBLPyTest, replicator: Replicator) -> ReplicatorStatus:
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
        manager = cblpytest.edge_servers[0]
        await manager.add_user(_LIMITED_USER, _LIMITED_PASSWORD, role="replicate")
        return manager.get_admin_client()

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

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_invalid_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        ESS-18: a session token that was never issued is rejected cleanly.
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
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Create a reusable session, then revoke it")
        token = await edge_server.create_session(_DB, one_time=False)
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

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_lost_on_edge_server_restart(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Edge Server sessions do not survive a restart, and the client fails cleanly.
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        manager = cblpytest.edge_servers[0]
        edge_server = await manager.configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Create a reusable session")
        token = await edge_server.create_session(_DB, one_time=False)

        self.mark_test_step("Restart Edge Server")
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
            await manager.reset_firewall()
            await replicator.stop()
            await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_one_time_session_expires(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        A one-time token stops working after its TTL, even if never presented.
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
         replicator authenticates with a one-time token
        """
        self.mark_test_step("Configure Edge Server with the `travel` dataset and CORS")
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=_DB, config_file=_CONFIG)

        self.mark_test_step("Create a one-time session")
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