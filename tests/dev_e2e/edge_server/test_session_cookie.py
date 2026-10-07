"""
Session-cookie replication tests.

See spec/tests/dev_e2e/014-session-cookie-replication.md.
"""

import asyncio
import tarfile
from pathlib import Path

import aiohttp
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.syncgateway import (
    DatabaseConfig,
    DocumentUpdateEntry,
    ScopeConfig,
)
from cbltest.asyncfile import read_json_file, write_json_file

SCRIPT_DIR = str(Path(__file__).parent)

SG_DB_NAME = "travel"
BUCKET_NAME = "travel"
SCOPE = "travel"
COLLECTION_NAME = "airlines"
COLLECTION = f"{SCOPE}.{COLLECTION_NAME}"
CHANNEL = "airlines"
RESTRICTED_CHANNEL = "restricted"
SG_USER = "session_user"
SG_PASSWORD = "password"

NEW_DOC_COUNT = 5

DEFAULT_SYNC = "function(doc){channel(doc.channels);}"
# Rejects a write unless the authenticated user matches doc.owner; documents without
# an owner (the pulled seed docs) skip the check. Used to prove a push ran as the user.
OWNER_SYNC = "function(doc){ if (doc.owner) { requireUser(doc.owner); } channel(doc.channels); }"


def _doc_name(doc_id: str) -> str:
    return f"Session Cookie Test Airline {doc_id}"


class TestSessionCookieBase(CBLTestClass):
    """Shared setup for the session-cookie tests."""

    async def _create_db_and_user(
        self,
        cblpytest: CBLPyTest,
        user_channels: list[str],
        sync_function: str = DEFAULT_SYNC,
    ) -> None:
        """Create the CBS bucket/collection, the SGW database, and `session_user`."""
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Creating travel bucket on Couchbase Server.")
        await server.create_bucket(BUCKET_NAME)
        server.create_collections(BUCKET_NAME, SCOPE, [COLLECTION_NAME])

        self.mark_test_step("Creating SGW database.")
        payload = DatabaseConfig(
            bucket=BUCKET_NAME,
            scopes={SCOPE: ScopeConfig(collections={COLLECTION_NAME: {"sync": sync_function}})},
            num_index_replicas=0,
        )
        await cblpytest.sync_gateway_cluster.create_database(SG_DB_NAME, payload)

        # Must precede create_session: SGW answers 404 for an unknown user.
        self.mark_test_step(f"Adding SGW user '{SG_USER}' with access to channels {user_channels}.")
        access_dict = sync_gateway.create_collection_access_dict({COLLECTION: user_channels})
        await sync_gateway.add_user(SG_DB_NAME, SG_USER, SG_PASSWORD, access_dict)

    async def _seed(
        self,
        cblpytest: CBLPyTest,
        doc_prefix: str,
        channel: str = CHANNEL,
        count: int = NEW_DOC_COUNT,
    ) -> set[str]:
        """Write `count` documents through SGW into `channel`; return their ids."""
        sync_gateway = cblpytest.sync_gateways[0]
        self.mark_test_step(f"Writing {count} documents to SGW channel '{channel}'.")
        doc_ids = [f"{doc_prefix}_{i}" for i in range(1, count + 1)]
        updates = [
            DocumentUpdateEntry(
                doc_id,
                None,
                {"channels": [channel], "type": "airline", "name": _doc_name(doc_id)},
            )
            for doc_id in doc_ids
        ]
        await sync_gateway.update_documents(SG_DB_NAME, updates, scope=SCOPE, collection=COLLECTION_NAME)
        await sync_gateway.wait_for_documents(SG_DB_NAME, doc_ids, scope=SCOPE, collection=COLLECTION_NAME)
        return set(doc_ids)

    async def _make_session(self, cblpytest: CBLPyTest, ttl: int | None = None) -> str:
        sync_gateway = cblpytest.sync_gateways[0]
        self.mark_test_step(f"Creating SGW session for '{SG_USER}'" + (f" (ttl={ttl}s)." if ttl else "."))
        session_id = await sync_gateway.create_session(SG_DB_NAME, SG_USER, ttl=ttl)
        assert session_id, "SGW returned an empty session id"
        return session_id

    async def _setup_sgw(self, cblpytest: CBLPyTest, doc_prefix: str) -> tuple[str, set[str]]:
        """Common setup: db + user + seeded docs + a session. Returns (session id, ids)."""
        await self._create_db_and_user(cblpytest, [CHANNEL])
        doc_ids = await self._seed(cblpytest, doc_prefix)
        session_id = await self._make_session(cblpytest)
        return session_id, doc_ids

    async def _check_sgw_access(
        self,
        cblpytest: CBLPyTest,
        *,
        expected_status: int,
        cookie_value: str | None = None,
    ) -> None:
        """GET /{db}/ against SGW's REST API and assert the status.

        With ``cookie_value`` set, this sends the same ``Cookie`` header ES will put on
        the handshake, so a failure isolates the fault to the session rather than ES.
        With ``cookie_value`` omitted, no credentials are sent — a 401 then proves guest
        access is off (a revoked cookie returns 401 even when guest access is on, so the
        cookie check alone cannot prove that).
        """
        sync_gateway = cblpytest.sync_gateways[0]
        headers = {"Cookie": cookie_value} if cookie_value else {}
        async with (
            aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session,
            session.get(f"{sync_gateway.public_url}/{SG_DB_NAME}/", headers=headers) as resp,
        ):
            status_code = resp.status
            resp_text = await resp.text()
        assert status_code == expected_status, (
            f"SGW returned {status_code} (expected {expected_status}) for "
            f"{'a cookie' if cookie_value else 'no-credentials'} request: {resp_text}"
        )

    async def _start_edge_server(
        self,
        cblpytest: CBLPyTest,
        tmp_path: Path,
        session_cookie: str | None = None,
        *,
        auth_override: dict | None = None,
    ) -> EdgeServer:
        """Write an ES config using `session_cookie` auth and start the server on it."""
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Configuring Edge Server with session_cookie auth.")
        config = await read_json_file(f"{SCRIPT_DIR}/config/test_session_cookie.json")
        config["replications"][0]["source"] = sync_gateway.replication_url(SG_DB_NAME)
        config["replications"][0]["auth"] = (
            auth_override if auth_override is not None else {"session_cookie": session_cookie}
        )

        config_path = str(tmp_path / "es_config.json")
        await write_json_file(config_path, config)

        es_manager = cblpytest.edge_servers[0]
        edge_server = await es_manager.configure_dataset(db_name="travel", config_file=config_path)
        # ES 1.1.0 accepts session_cookie but never sends it.
        await self.skip_if_es_not(edge_server, ">= 1.1.1")
        return edge_server

    async def _assert_replicator_created(self, edge_server: EdgeServer) -> bool:
        """Poll briefly for the replicator to appear. Returns whether it was created."""
        for _ in range(15):
            if len(await edge_server.all_replication_status()) > 0:
                return True
            await asyncio.sleep(1)
        return False

    async def _assert_replication_works(self, edge_server: EdgeServer, expected_doc_ids: set[str]) -> None:
        """Assert the replicator was created and pulled the seeded documents."""
        self.mark_test_step("Verifying the replicator was created.")
        assert await self._assert_replicator_created(edge_server), (
            "No replicators found on Edge Server — the replication config was rejected. "
            "Check the session_cookie value and format."
        )

        self.mark_test_step("Waiting for the seeded documents to reach Edge Server.")
        arrived = await edge_server.wait_for_documents("travel", expected_doc_ids, collection=COLLECTION, timeout=30)
        missing = expected_doc_ids - arrived
        assert not missing, (
            f"Documents {sorted(missing)} did not replicate to Edge Server. "
            "Session-cookie auth did not authenticate the replication."
        )

    async def _assert_handshake_rejected(self, cblpytest: CBLPyTest, failures_before: int, timeout: int = 20) -> None:
        """Poll until SGW's auth_failed_count rises above `failures_before`.

        A positive signal that ES actually attempted (and SGW rejected) a handshake —
        "no documents arrived" alone also holds when ES never created a replicator.
        """
        sync_gateway = cblpytest.sync_gateways[0]
        for _ in range(timeout):
            if await sync_gateway.get_auth_failed_count(SG_DB_NAME) > failures_before:
                return
            await asyncio.sleep(1)
        raise AssertionError(
            "SGW's auth_failed_count did not increase — Edge Server never attempted an "
            "authenticated handshake (the replication config may have been rejected outright)."
        )


@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.min_edge_servers(1)
class TestSessionCookie(TestSessionCookieBase):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_cookie_replication(self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path) -> None:
        """ES replicates with SGW using a bare session id; ES supplies the prefix."""
        doc_prefix = "session_cookie_airline"
        session_id, seeded_doc_ids = await self._setup_sgw(cblpytest, doc_prefix)
        await self._check_sgw_access(cblpytest, cookie_value=f"SyncGatewaySession={session_id}", expected_status=200)

        edge_server = await self._start_edge_server(cblpytest, tmp_path, session_id)
        await self._assert_replication_works(edge_server, seeded_doc_ids)

        self.mark_test_step("Verifying a seeded document replicated with its body intact.")
        seeded_id = f"{doc_prefix}_1"
        edge_doc = await edge_server.get_document("travel", collection=COLLECTION, doc_id=seeded_id)
        assert edge_doc is not None, f"Seeded document {seeded_id} not retrievable from Edge Server."
        assert edge_doc.body.get("name") == _doc_name(seeded_id), (
            f"Seeded document body did not replicate correctly: {edge_doc.body}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_cookie_already_prefixed(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        """ES replicates when the configured value already carries the prefix."""
        doc_prefix = "session_cookie_prefixed_airline"
        session_id, seeded_doc_ids = await self._setup_sgw(cblpytest, doc_prefix)
        prefixed = f"SyncGatewaySession={session_id}"
        await self._check_sgw_access(cblpytest, cookie_value=prefixed, expected_status=200)

        edge_server = await self._start_edge_server(cblpytest, tmp_path, prefixed)
        await self._assert_replication_works(edge_server, seeded_doc_ids)


@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.min_edge_servers(1)
class TestSessionCookieRevocation(TestSessionCookieBase):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_revoked_session_cannot_start_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        """A revoked session cannot establish replication."""
        sync_gateway = cblpytest.sync_gateways[0]

        doc_prefix = "session_cookie_revoke_airline"
        session_id, seeded_doc_ids = await self._setup_sgw(cblpytest, doc_prefix)

        # Revoked before ES connects, so the handshake itself is what gets rejected.
        self.mark_test_step("Revoking the SGW session before Edge Server connects.")
        await sync_gateway.delete_session(SG_DB_NAME, session_id)

        self.mark_test_step("Confirming the revoked session is rejected by SGW.")
        await self._check_sgw_access(cblpytest, cookie_value=f"SyncGatewaySession={session_id}", expected_status=401)

        self.mark_test_step("Confirming guest access is off (no-credentials request is rejected).")
        await self._check_sgw_access(cblpytest, cookie_value=None, expected_status=401)

        self.mark_test_step("Recording SGW's auth-failure count before starting Edge Server.")
        failures_before = await sync_gateway.get_auth_failed_count(SG_DB_NAME)

        self.mark_test_step("Starting Edge Server with the revoked session cookie.")
        edge_server = await self._start_edge_server(cblpytest, tmp_path, session_id)

        self.mark_test_step("Verifying SGW rejected an Edge Server handshake attempt.")
        await self._assert_handshake_rejected(cblpytest, failures_before)

        self.mark_test_step("Verifying the seeded documents did not reach Edge Server.")
        response = await edge_server.get_all_documents("travel", collection=COLLECTION)
        arrived = seeded_doc_ids & {row.id for row in response.rows}
        assert not arrived, (
            f"Documents {sorted(arrived)} replicated using a revoked session cookie — "
            "the cookie is not actually gating replication."
        )


@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.min_edge_servers(1)
class TestSessionCookieChannelAccess(TestSessionCookieBase):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_replicates_only_the_users_channels(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        """The replication runs as session_user: only that user's channel replicates.

        Seeds documents in an allowed channel and a restricted one; the session user
        has access to the allowed channel only, so guest/other-user access (or a cookie
        that fell through to a wider identity) would show up as the restricted docs
        arriving.
        """
        await self._create_db_and_user(cblpytest, [CHANNEL])
        allowed_ids = await self._seed(cblpytest, "allowed_airline", channel=CHANNEL)
        denied_ids = await self._seed(cblpytest, "denied_airline", channel=RESTRICTED_CHANNEL)
        session_id = await self._make_session(cblpytest)
        await self._check_sgw_access(cblpytest, cookie_value=f"SyncGatewaySession={session_id}", expected_status=200)

        edge_server = await self._start_edge_server(cblpytest, tmp_path, session_id)
        await self._assert_replication_works(edge_server, allowed_ids)

        self.mark_test_step("Verifying restricted-channel documents did NOT replicate.")
        response = await edge_server.get_all_documents("travel", collection=COLLECTION)
        leaked = denied_ids & {row.id for row in response.rows}
        assert not leaked, (
            f"Documents {sorted(leaked)} from channel '{RESTRICTED_CHANNEL}' replicated, but "
            f"'{SG_USER}' has no access to it — the replication is not scoped to the session user."
        )


@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.min_edge_servers(1)
class TestSessionCookiePush(TestSessionCookieBase):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_cookie_push(self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path) -> None:
        """A document written on ES pushes to SGW, authenticated as the session user.

        The collection's sync function calls requireUser(doc.owner), so SGW accepts the
        pushed document only if the replication authenticated as its owner — proving the
        push ran as session_user, not as guest or another identity.
        """
        sync_gateway = cblpytest.sync_gateways[0]

        await self._create_db_and_user(cblpytest, [CHANNEL], sync_function=OWNER_SYNC)
        session_id = await self._make_session(cblpytest)
        await self._check_sgw_access(cblpytest, cookie_value=f"SyncGatewaySession={session_id}", expected_status=200)

        edge_server = await self._start_edge_server(cblpytest, tmp_path, session_id)
        assert await self._assert_replicator_created(edge_server), "Replicator was not created."

        self.mark_test_step("Writing a document on Edge Server owned by the session user.")
        push_id = "session_cookie_push_1"
        body = {"channels": [CHANNEL], "owner": SG_USER, "type": "airline", "name": _doc_name(push_id)}
        await edge_server.put_document_with_id(body, push_id, "travel", collection=COLLECTION)

        self.mark_test_step("Verifying the document was pushed to SGW as the session user.")
        try:
            await sync_gateway.wait_for_documents(SG_DB_NAME, [push_id], scope=SCOPE, collection=COLLECTION_NAME)
        except Exception as e:
            raise AssertionError(
                f"Document {push_id} did not push to SGW — session-cookie auth did not "
                "authenticate the push as the session user."
            ) from e


@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.min_edge_servers(1)
class TestSessionCookieBadValues(TestSessionCookieBase):
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "label,cookie_value",
        [
            ("empty", ""),
            ("unknown-id", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"),
        ],
    )
    async def test_bad_session_cookie_cannot_replicate(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path, label: str, cookie_value: str
    ) -> None:
        """An empty or unknown session cookie does not result in authenticated replication.

        A bad value is handled one of two valid ways: ES rejects the config outright (no
        replicator), or ES attempts a handshake that SGW rejects. Either is acceptable;
        what must never happen is documents replicating. We assert the positive evidence
        (config rejected OR handshake rejected) so "no documents" is not a false pass from
        ES simply never connecting.
        """
        sync_gateway = cblpytest.sync_gateways[0]
        _session_id, seeded_doc_ids = await self._setup_sgw(cblpytest, f"bad_{label}_airline")

        failures_before = await sync_gateway.get_auth_failed_count(SG_DB_NAME)
        edge_server = await self._start_edge_server(cblpytest, tmp_path, cookie_value)

        if await self._assert_replicator_created(edge_server):
            self.mark_test_step(f"Replicator created; verifying SGW rejected the '{label}' handshake.")
            await self._assert_handshake_rejected(cblpytest, failures_before)
        else:
            self.mark_test_step(f"The '{label}' cookie config was rejected outright (no replicator).")

        self.mark_test_step("Verifying no documents replicated.")
        response = await edge_server.get_all_documents("travel", collection=COLLECTION)
        arrived = seeded_doc_ids & {row.id for row in response.rows}
        assert not arrived, f"Documents {sorted(arrived)} replicated with a '{label}' session cookie."

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_cookie_and_basic_auth_conflict_is_rejected(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        """Configuring both session_cookie and basic auth is rejected: no replicator."""
        session_id, _seeded = await self._setup_sgw(cblpytest, "conflict_airline")

        edge_server = await self._start_edge_server(
            cblpytest,
            tmp_path,
            auth_override={"session_cookie": session_id, "user": SG_USER, "password": SG_PASSWORD},
        )

        self.mark_test_step("Verifying the conflicting-auth replication config was rejected.")
        assert not await self._assert_replicator_created(edge_server), (
            "Edge Server created a replicator for a config with both session_cookie and "
            "basic auth; conflicting auth types should be rejected."
        )


@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.min_edge_servers(1)
class TestSessionCookieRestart(TestSessionCookieBase):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_cookie_survives_restart(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        """Replication resumes with the stored session cookie after an ES restart."""
        es_manager = cblpytest.edge_servers[0]

        session_id, seeded_doc_ids = await self._setup_sgw(cblpytest, "restart_airline")
        edge_server = await self._start_edge_server(cblpytest, tmp_path, session_id)
        await self._assert_replication_works(edge_server, seeded_doc_ids)

        self.mark_test_step("Restarting Edge Server without wiping its database.")
        await es_manager.kill_server()
        edge_server = await es_manager.start_server()

        self.mark_test_step("Writing a new document to SGW after the restart.")
        new_ids = await self._seed(cblpytest, "restart_after_airline", count=1)

        self.mark_test_step("Verifying replication resumed and delivered the new document.")
        arrived = await edge_server.wait_for_documents("travel", new_ids, collection=COLLECTION, timeout=45)
        missing = new_ids - arrived
        assert not missing, (
            f"Documents {sorted(missing)} did not replicate after restart — the stored "
            "session cookie did not resume replication."
        )


@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.min_edge_servers(1)
class TestSessionCookieLogRedaction(TestSessionCookieBase):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_id_not_leaked_in_logs(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        """The session id (a bearer credential) must not appear in Edge Server logs."""
        es_manager = cblpytest.edge_servers[0]

        session_id, seeded_doc_ids = await self._setup_sgw(cblpytest, "redaction_airline")
        edge_server = await self._start_edge_server(cblpytest, tmp_path, session_id)
        await self._assert_replication_works(edge_server, seeded_doc_ids)

        self.mark_test_step("Collecting Edge Server logs.")
        archive = await es_manager.collect_logs(tmp_path)
        extract_dir = tmp_path / "es_logs"
        with tarfile.open(archive) as tar:
            tar.extractall(extract_dir, filter="data")

        # The bundle also contains the live config, which legitimately holds the cookie,
        # so only the actual log files are searched — not the config.
        self.mark_test_step("Verifying the session id does not appear in any log file.")
        needle = session_id.encode()
        log_suffixes = {".cbllog", ".log", ".txt"}
        leaked_in: list[str] = []
        for path in extract_dir.rglob("*"):
            if path.is_file() and path.suffix in log_suffixes and needle in path.read_bytes():
                leaked_in.append(str(path.relative_to(extract_dir)))
        assert not leaked_in, (
            f"Session id leaked into Edge Server logs: {leaked_in}. A session cookie is a "
            "bearer credential and must be redacted from logs."
        )


@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.min_edge_servers(1)
class TestSessionCookieReconnect(TestSessionCookieBase):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_revoked_session_fails_on_reconnect(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        """Revoking a connected session blocks the next handshake after a reconnect.

        Revocation does not tear down an already-authenticated BLIP stream, so the fault
        only shows on the next handshake. We take ES offline (kill), revoke, write a
        document while it is down, then bring it back (start) to force a fresh handshake
        with the now-revoked cookie. A disconnect/reconnect window driven this way is
        deterministic, where a firewall deny/allow is subject to ES's reconnect backoff.
        The restart handshake must be rejected and the offline document must not arrive.
        """
        sync_gateway = cblpytest.sync_gateways[0]
        es_manager = cblpytest.edge_servers[0]

        session_id, seeded_doc_ids = await self._setup_sgw(cblpytest, "reconnect_airline")
        edge_server = await self._start_edge_server(cblpytest, tmp_path, session_id)
        await self._assert_replication_works(edge_server, seeded_doc_ids)

        self.mark_test_step("Taking Edge Server offline and revoking the session.")
        await es_manager.kill_server()
        await sync_gateway.delete_session(SG_DB_NAME, session_id)

        self.mark_test_step("Writing a document to SGW while Edge Server is offline.")
        offline_ids = await self._seed(cblpytest, "reconnect_offline_airline", count=1)

        self.mark_test_step("Recording SGW's auth-failure count before Edge Server reconnects.")
        failures_before = await sync_gateway.get_auth_failed_count(SG_DB_NAME)

        self.mark_test_step("Restarting Edge Server to force a reconnect handshake.")
        edge_server = await es_manager.start_server()

        self.mark_test_step("Verifying the reconnect handshake was rejected by SGW.")
        await self._assert_handshake_rejected(cblpytest, failures_before, timeout=45)

        self.mark_test_step("Verifying the offline document did not replicate after reconnect.")
        arrived = await edge_server.wait_for_documents("travel", offline_ids, collection=COLLECTION, timeout=15)
        assert not (offline_ids & arrived), (
            f"Documents {sorted(offline_ids & arrived)} replicated after the session was "
            "revoked — the revoked cookie still authenticated the reconnect."
        )


@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.min_edge_servers(1)
class TestSessionCookieExpiry(TestSessionCookieBase):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_expired_session_cannot_start_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        """An expired session cannot establish replication (distinct SGW path from revoke)."""
        sync_gateway = cblpytest.sync_gateways[0]

        ttl = 5
        await self._create_db_and_user(cblpytest, [CHANNEL])
        seeded_doc_ids = await self._seed(cblpytest, "expired_airline")
        session_id = await self._make_session(cblpytest, ttl=ttl)

        self.mark_test_step(f"Waiting {ttl + 3}s for the session to expire.")
        await asyncio.sleep(ttl + 3)

        self.mark_test_step("Confirming the expired session is rejected by SGW.")
        await self._check_sgw_access(cblpytest, cookie_value=f"SyncGatewaySession={session_id}", expected_status=401)

        failures_before = await sync_gateway.get_auth_failed_count(SG_DB_NAME)
        edge_server = await self._start_edge_server(cblpytest, tmp_path, session_id)

        self.mark_test_step("Verifying SGW rejected the expired-session handshake.")
        await self._assert_handshake_rejected(cblpytest, failures_before)

        self.mark_test_step("Verifying no documents replicated.")
        response = await edge_server.get_all_documents("travel", collection=COLLECTION)
        arrived = seeded_doc_ids & {row.id for row in response.rows}
        assert not arrived, f"Documents {sorted(arrived)} replicated with an expired session cookie."
