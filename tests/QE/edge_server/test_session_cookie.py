import asyncio
import secrets
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.error import CblEdgeServerBadResponseError, CblSyncGatewayBadResponseError
from cbltest.api.syncgateway import (
    SYNC_GATEWAY_SESSION_COOKIE,
    DatabaseConfig,
    ScopeConfig,
    get_sync_gateway_session_headers,
)
from cbltest.asyncfile import read_json_file, write_json_file

SCRIPT_DIR = str(Path(__file__).parent)

BUCKET = "travel"
SG_DB = "travel"
ES_DB = "travel"
SCOPE = "travel"
COLLECTIONS = ["airlines", "hotels"]
SESSION_USER = "session_user"
SESSION_CHANNEL = "session_ch"
RESTRICTED_CHANNEL = "restricted_ch"
SYNC_FUNCTION = "function(doc, oldDoc, meta) { if (doc.owner) { requireUser(doc.owner); } channel(doc.channels); }"


@pytest.mark.min_edge_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestSessionCookie(CBLTestClass):
    async def _setup_sgw(self, cblpytest: CBLPyTest) -> None:
        """Create the guest-less `travel` database with `session_user`, and check guest is refused."""
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step("Create the SGW `travel` database with guest disabled and the `requireUser` sync function")
        await server.create_bucket(BUCKET)
        server.create_collections(BUCKET, SCOPE, COLLECTIONS)
        config = DatabaseConfig(
            bucket=BUCKET,
            scopes={SCOPE: ScopeConfig(collections={c: {"sync": SYNC_FUNCTION} for c in COLLECTIONS})},
            guest={"disabled": True},
            num_index_replicas=0,
        )
        await cblpytest.sync_gateway_cluster.create_database(SG_DB, config)

        self.mark_test_step("Add `session_user` with access to `session_ch` in both collections")
        access = sync_gateway.create_collection_access_dict({f"{SCOPE}.{c}": [SESSION_CHANNEL] for c in COLLECTIONS})
        await sync_gateway.add_user(SG_DB, SESSION_USER, "password", access)

        self.mark_test_step("Verify SGW rejects an unauthenticated request")
        assert await self._sgw_status(cblpytest, None) == 401, "SGW allows guest access"

    async def _sgw_status(self, cblpytest: CBLPyTest, session_id: str | None) -> int:
        """The status SGW answers `_all_docs` with for `session_id`, or for no credentials if None."""
        headers = get_sync_gateway_session_headers(session_id) if session_id else {}
        async with cblpytest.sync_gateways[0].get_user_client(headers) as client:
            try:
                await client.get_all_documents(SG_DB, scope=SCOPE, collection=COLLECTIONS[0])
            except CblSyncGatewayBadResponseError as e:
                return e.code
            return 200

    async def _seed_docs(self, cblpytest: CBLPyTest, prefix: str, channel: str = SESSION_CHANNEL) -> list[str]:
        """Write 3 documents in `channel` to each collection through CBS, and wait for SGW to import them."""
        server = cblpytest.couchbase_servers[0]
        doc_ids = [f"{prefix}_{i}" for i in range(3)]
        for collection in COLLECTIONS:
            for doc_id in doc_ids:
                server.upsert_document(BUCKET, doc_id, {"channels": [channel]}, scope=SCOPE, collection=collection)
            await cblpytest.sync_gateways[0].wait_for_documents(SG_DB, doc_ids, scope=SCOPE, collection=collection)
        return doc_ids

    async def _es_config(
        self, cblpytest: CBLPyTest, tmp_path: Path, session_cookie: str, cookie_header: str | None = None
    ) -> str:
        """Write an Edge Server config that replicates with SGW using `session_cookie`."""
        config = await read_json_file(f"{SCRIPT_DIR}/config/test_session_cookie.json")
        replication = config["replications"][0]
        replication["source"] = cblpytest.sync_gateways[0].replication_url(SG_DB)
        replication["auth"]["session_cookie"] = session_cookie
        if cookie_header:
            replication["headers"] = {"Cookie": cookie_header}
        config_path = str(tmp_path / f"es_config_{session_cookie[-8:]}.json")
        await write_json_file(config_path, config)
        return config_path

    async def _es_doc_ids(self, edge_server: EdgeServer, collection: str) -> set[str]:
        """The ids of every document in `collection` on Edge Server."""
        response = await edge_server.get_all_documents(ES_DB, collection=f"{SCOPE}.{collection}")
        return {row.id for row in response.rows}

    @pytest.mark.parametrize(
        "prefixed, cookie_header",
        [
            pytest.param(False, None, id="bare"),
            pytest.param(True, None, id="prefixed"),
            pytest.param(False, "AWSALB=qe-sticky-session", id="with_unrelated_cookie_header"),
        ],
    )
    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_cookie_bidirectional_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path, prefixed: bool, cookie_header: str | None
    ) -> None:
        sync_gateway = cblpytest.sync_gateways[0]
        await self._setup_sgw(cblpytest)

        self.mark_test_step("Seed `session_ch` and `restricted_ch` documents into both collections")
        visible = await self._seed_docs(cblpytest, "visible")
        restricted = await self._seed_docs(cblpytest, "restricted", RESTRICTED_CHANNEL)

        self.mark_test_step("Create a session for `session_user` and verify SGW accepts it")
        session_id = await sync_gateway.create_session(SG_DB, SESSION_USER)
        assert await self._sgw_status(cblpytest, session_id) == 200, "SGW rejected a session it just issued"

        self.mark_test_step("Start Edge Server replicating with the session")
        session_cookie = f"{SYNC_GATEWAY_SESSION_COOKIE}={session_id}" if prefixed else session_id
        config_path = await self._es_config(cblpytest, tmp_path, session_cookie, cookie_header)
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=ES_DB, config_file=config_path)
        await edge_server.wait_for_idle()

        self.mark_test_step("Verify only the `session_ch` documents were pulled")
        for collection in COLLECTIONS:
            es_ids = await self._es_doc_ids(edge_server, collection)
            assert set(visible) <= es_ids, f"Missing from Edge Server {collection}: {set(visible) - es_ids}"
            assert es_ids.isdisjoint(restricted), f"Pulled restricted documents into {collection}"

        self.mark_test_step("On Edge Server, write `foreign` (owner `other_user`), then `owned` (owner `session_user`)")
        await edge_server.put_document_with_id(
            {"owner": "other_user", "channels": [SESSION_CHANNEL]}, "foreign", ES_DB, SCOPE, COLLECTIONS[0]
        )
        for collection in COLLECTIONS:
            await edge_server.put_document_with_id(
                {"owner": SESSION_USER, "channels": [SESSION_CHANNEL]}, "owned", ES_DB, SCOPE, collection
            )

        self.mark_test_step("Verify `owned` reached SGW in both collections")
        for collection in COLLECTIONS:
            await sync_gateway.wait_for_documents(SG_DB, ["owned"], scope=SCOPE, collection=collection)

        self.mark_test_step("Verify `foreign` was rejected by `requireUser`: the push was made as `session_user`")
        sgw_docs = await sync_gateway.get_all_documents(SG_DB, scope=SCOPE, collection=COLLECTIONS[0])
        assert "foreign" not in {row.id for row in sgw_docs.rows}, "Push was not authenticated as session_user"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_cookie_across_restart_revoke_and_rotate(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        sync_gateway = cblpytest.sync_gateways[0]
        es_manager = cblpytest.edge_servers[0]
        await self._setup_sgw(cblpytest)

        self.mark_test_step("Seed phase 1 documents, then start Edge Server with session A")
        phase1 = await self._seed_docs(cblpytest, "phase1")
        session_a = await sync_gateway.create_session(SG_DB, SESSION_USER)
        config_a = await self._es_config(cblpytest, tmp_path, session_a)
        edge_server = await es_manager.configure_dataset(db_name=ES_DB, config_file=config_a)
        await edge_server.wait_for_idle()
        assert set(phase1) <= await self._es_doc_ids(edge_server, COLLECTIONS[0]), "Phase 1 not pulled"

        self.mark_test_step("Stop Edge Server, seed phase 2 documents, and restart it on the same config")
        await es_manager.kill_server()
        phase2 = await self._seed_docs(cblpytest, "phase2")
        edge_server = await es_manager.start_server()
        await edge_server.wait_for_idle()
        assert set(phase2) <= await self._es_doc_ids(edge_server, COLLECTIONS[0]), "Phase 2 not pulled after restart"

        self.mark_test_step("Stop Edge Server, revoke session A, and verify SGW rejects it")
        await es_manager.kill_server()
        await sync_gateway.delete_session(SG_DB, session_a)
        assert await self._sgw_status(cblpytest, session_a) == 401, "SGW still accepts the revoked session"

        self.mark_test_step("Seed phase 3 documents, restart Edge Server, and verify the replicator fails with a 401")
        phase3 = await self._seed_docs(cblpytest, "phase3")
        edge_server = await es_manager.start_server()
        with pytest.raises(CblEdgeServerBadResponseError) as e:
            await edge_server.wait_for_idle(timeout=10)
        assert e.value.code in (401, 404), f"Replicator failed, but not on a 401: {e.value.body}"
        assert not set(phase3) & await self._es_doc_ids(edge_server, COLLECTIONS[0]), "Pulled with a revoked session"

        self.mark_test_step("On Edge Server, write `offline_write` while the replicator is down")
        await edge_server.put_document_with_id(
            {"owner": SESSION_USER, "channels": [SESSION_CHANNEL]}, "offline_write", ES_DB, SCOPE, COLLECTIONS[0]
        )

        self.mark_test_step("Restart Edge Server with a new session B")
        session_b = await sync_gateway.create_session(SG_DB, SESSION_USER)
        config_b = await self._es_config(cblpytest, tmp_path, session_b)
        await es_manager.kill_server()
        edge_server = await es_manager.start_server(config_b)
        await edge_server.wait_for_idle()

        self.mark_test_step("Verify phase 3 was pulled and `offline_write` was pushed")
        assert set(phase3) <= await self._es_doc_ids(edge_server, COLLECTIONS[0]), "Phase 3 not pulled with session B"
        await sync_gateway.wait_for_documents(SG_DB, ["offline_write"], scope=SCOPE, collection=COLLECTIONS[0])

    @pytest.mark.parametrize("session_kind", ["expired", "never_issued"])
    @pytest.mark.asyncio(loop_scope="session")
    async def test_invalid_session_cookie_rejected(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path, session_kind: str
    ) -> None:
        sync_gateway = cblpytest.sync_gateways[0]
        await self._setup_sgw(cblpytest)

        self.mark_test_step("Seed documents")
        seeded = await self._seed_docs(cblpytest, session_kind)

        self.mark_test_step("Obtain the parameter's session and verify SGW rejects it")
        if session_kind == "expired":
            session_id = await sync_gateway.create_session(SG_DB, SESSION_USER, ttl=5)
            await asyncio.sleep(10)
        else:
            session_id = secrets.token_hex(20)
        assert await self._sgw_status(cblpytest, session_id) == 401, f"SGW accepts an {session_kind} session"

        self.mark_test_step("Start Edge Server with the session, and verify the replicator fails with a 401")
        config_path = await self._es_config(cblpytest, tmp_path, session_id)
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=ES_DB, config_file=config_path)
        with pytest.raises(CblEdgeServerBadResponseError) as e:
            await edge_server.wait_for_idle(timeout=10)
        assert e.value.code in (401, 404), f"Replicator failed, but not on a 401: {e.value.body}"

        self.mark_test_step("Verify none of the seeded documents were pulled")
        assert not set(seeded) & await self._es_doc_ids(edge_server, COLLECTIONS[0]), "Pulled with a bad session"
