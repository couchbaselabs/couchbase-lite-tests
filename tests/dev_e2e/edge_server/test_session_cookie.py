"""
Session-cookie replication tests (CBL-8647).

See spec/tests/dev_e2e/014-session-cookie-replication.md.
"""

import asyncio
from pathlib import Path

import aiohttp
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.syncgateway import DatabaseConfig, ScopeConfig
from cbltest.asyncfile import read_json_file, write_json_file

SCRIPT_DIR = str(Path(__file__).parent)

SG_DB_NAME = "travel"
BUCKET_NAME = "travel"
COLLECTION = "travel.airlines"
SG_USER = "session_user"
SG_PASSWORD = "password"

PRELOADED_DOC_COUNT = 150
NEW_DOC_COUNT = 5


class TestSessionCookieBase(CBLTestClass):
    """Shared setup for the session-cookie tests."""

    @staticmethod
    def _seeded_doc_ids(doc_prefix: str) -> set[str]:
        return {f"{doc_prefix}_{i}" for i in range(1, NEW_DOC_COUNT + 1)}

    async def _setup_sgw(self, cblpytest: CBLPyTest, doc_prefix: str) -> str:
        """Stand up CBS + SGW with documents to replicate, and return a session id."""
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Creating travel bucket on Couchbase Server.")
        server.create_bucket(BUCKET_NAME)
        server.create_collections(BUCKET_NAME, "travel", ["airlines"])

        self.mark_test_step("Creating SGW database.")
        payload = DatabaseConfig(
            bucket=BUCKET_NAME,
            scopes={"travel": ScopeConfig(collections={"airlines": {"sync": "function(doc){channel(doc.channels);}"}})},
            num_index_replicas=0,
        )
        await cblpytest.sync_gateway_cluster.create_database(SG_DB_NAME, payload)

        # Must precede create_session: SGW answers 404 for an unknown user.
        self.mark_test_step(f"Adding SGW user '{SG_USER}' with channel access.")
        access_dict = sync_gateway.create_collection_access_dict({COLLECTION: ["*"]})
        await sync_gateway.add_user(SG_DB_NAME, SG_USER, SG_PASSWORD, access_dict)

        self.mark_test_step(f"Adding {NEW_DOC_COUNT} documents to CBS bucket.")
        doc_ids = [f"{doc_prefix}_{i}" for i in range(1, NEW_DOC_COUNT + 1)]
        for doc_id in doc_ids:
            server.upsert_document(
                BUCKET_NAME,
                doc_id,
                {
                    "id": doc_id,
                    "channels": ["*"],
                    "type": "airline",
                    "name": f"Session Cookie Test Airline {doc_id}",
                },
                scope="travel",
                collection="airlines",
            )

        self.mark_test_step("Waiting for SGW to import documents from CBS.")
        await sync_gateway.wait_for_documents(SG_DB_NAME, doc_ids, scope="travel", collection="airlines")

        self.mark_test_step(f"Creating SGW session for '{SG_USER}'.")
        session_id = await sync_gateway.create_session(SG_DB_NAME, SG_USER)
        assert session_id, "SGW returned an empty session id"
        return session_id

    async def _verify_session_against_sgw(self, cblpytest: CBLPyTest, cookie_value: str) -> None:
        """Check the cookie against SGW's REST API before involving Edge Server."""
        sync_gateway = cblpytest.sync_gateways[0]
        self.mark_test_step("Verifying session cookie against SGW REST API.")
        async with (
            aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session,
            session.get(
                f"{sync_gateway.public_url}/{SG_DB_NAME}/",
                headers={"Cookie": cookie_value},
            ) as resp,
        ):
            status_code = resp.status
            resp_text = await resp.text()
        assert status_code == 200, (
            f"Session cookie rejected by SGW before Edge Server was involved: {status_code} {resp_text}"
        )

    async def _start_edge_server(self, cblpytest: CBLPyTest, tmp_path: Path, session_cookie: str) -> EdgeServer:
        """Write an ES config using `session_cookie` auth and start the server on it."""
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Configuring Edge Server with session_cookie auth.")
        config = await read_json_file(f"{SCRIPT_DIR}/config/test_session_cookie.json")
        config["replications"][0]["source"] = sync_gateway.replication_url(SG_DB_NAME)
        config["replications"][0]["auth"] = {"session_cookie": session_cookie}

        config_path = str(tmp_path / "es_config.json")
        await write_json_file(config_path, config)

        es_manager = cblpytest.edge_servers[0]
        return await es_manager.configure_dataset(db_name="travel", config_file=config_path)

    async def _assert_replication_works(self, edge_server: EdgeServer, expected_doc_ids: set[str]) -> None:
        """Assert the replicator started, reached idle, and pulled the seeded documents."""
        await asyncio.sleep(1)

        self.mark_test_step("Verifying the replicator was created.")
        repl_status = await edge_server.all_replication_status()
        assert len(repl_status) > 0, (
            "No replicators found on Edge Server — the replication config was rejected. "
            "Check the session_cookie value and format."
        )

        self.mark_test_step("Waiting for replication to be idle.")
        await edge_server.wait_for_idle(timeout=15)

        self.mark_test_step("Verifying the seeded documents reached Edge Server.")
        max_wait, poll_interval, elapsed = 30, 3, 0
        arrived: set[str] = set()
        total = 0
        while elapsed < max_wait:
            response = await edge_server.get_all_documents("travel", collection=COLLECTION)
            total = len(response.rows)
            arrived = expected_doc_ids & {row.id for row in response.rows}
            if arrived == expected_doc_ids:
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        missing = expected_doc_ids - arrived
        assert not missing, (
            f"Documents {sorted(missing)} did not replicate to Edge Server "
            f"({total} docs present, {PRELOADED_DOC_COUNT} of which ship pre-loaded). "
            "Session-cookie auth did not authenticate the replication."
        )


@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
@pytest.mark.min_edge_servers(1)
class TestSessionCookie(TestSessionCookieBase):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_cookie_replication(self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path) -> None:
        """ES replicates with SGW using a bare session id; ES supplies the prefix."""
        doc_prefix = "session_cookie_airline"
        session_id = await self._setup_sgw(cblpytest, doc_prefix)
        seeded_doc_ids = self._seeded_doc_ids(doc_prefix)
        await self._verify_session_against_sgw(cblpytest, f"SyncGatewaySession={session_id}")

        edge_server = await self._start_edge_server(cblpytest, tmp_path, session_id)
        await self._assert_replication_works(edge_server, seeded_doc_ids)

        self.mark_test_step("Verifying a document is retrievable from Edge Server.")
        response = await edge_server.get_all_documents("travel", collection=COLLECTION)
        assert len(response.rows) > 0, "No documents found on Edge Server."
        first_doc_id = response.rows[0].id
        edge_doc = await edge_server.get_document("travel", collection=COLLECTION, doc_id=first_doc_id)
        assert edge_doc is not None, f"Document {first_doc_id} not retrievable from Edge Server."
        assert "name" in edge_doc.body, f"Document missing 'name' field: {edge_doc.body}"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_cookie_already_prefixed(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        """ES replicates when the configured value already carries the prefix."""
        doc_prefix = "session_cookie_prefixed_airline"
        session_id = await self._setup_sgw(cblpytest, doc_prefix)
        seeded_doc_ids = self._seeded_doc_ids(doc_prefix)
        prefixed = f"SyncGatewaySession={session_id}"
        await self._verify_session_against_sgw(cblpytest, prefixed)

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
        session_id = await self._setup_sgw(cblpytest, doc_prefix)
        seeded_doc_ids = self._seeded_doc_ids(doc_prefix)

        # Revoked before ES connects, so the handshake itself is what gets rejected.
        self.mark_test_step("Revoking the SGW session before Edge Server connects.")
        await sync_gateway.delete_session(SG_DB_NAME, session_id)

        self.mark_test_step("Confirming the revoked session is rejected by SGW.")
        async with (
            aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session,
            session.get(
                f"{sync_gateway.public_url}/{SG_DB_NAME}/",
                headers={"Cookie": f"SyncGatewaySession={session_id}"},
            ) as resp,
        ):
            assert resp.status == 401, (
                f"Expected 401 for a revoked session, got {resp.status}. "
                "If SGW is allowing guest access this test cannot prove anything."
            )

        self.mark_test_step("Starting Edge Server with the revoked session cookie.")
        edge_server = await self._start_edge_server(cblpytest, tmp_path, session_id)

        self.mark_test_step("Verifying the seeded documents do not reach Edge Server.")
        await asyncio.sleep(20)

        response = await edge_server.get_all_documents("travel", collection=COLLECTION)
        arrived = seeded_doc_ids & {row.id for row in response.rows}
        assert not arrived, (
            f"Documents {sorted(arrived)} replicated using a revoked session cookie — "
            "the cookie is not actually gating replication."
        )
