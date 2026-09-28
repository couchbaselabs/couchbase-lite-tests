import asyncio
import secrets
from pathlib import Path
from typing import Any

import aiohttp
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.error import CblEdgeServerBadResponseError
from cbltest.api.syncgateway import DatabaseConfig, ScopeConfig
from cbltest.asyncfile import read_json_file, write_json_file

SCRIPT_DIR = str(Path(__file__).parent)
CONFIG_TEMPLATE = f"{SCRIPT_DIR}/config/test_session_cookie.json"

BUCKET = "travel"
SG_DB = "travel"
ES_DB = "travel"
SCOPE = "travel"
COLLECTIONS = ("airlines", "hotels")

SESSION_USER = "session_user"
SESSION_USER_PASSWORD = "password"
SESSION_CHANNEL = "session_ch"
RESTRICTED_CHANNEL = "restricted_ch"
COOKIE_NAME = "SyncGatewaySession"
UNRELATED_COOKIE = "AWSALB=qe-sticky-session"

VISIBLE_PER_COLLECTION = 3
RESTRICTED_PER_COLLECTION = 2
EXPIRED_SESSION_TTL = 5

SYNC_FUNCTION = "function(doc, oldDoc, meta) { if (doc.owner) { requireUser(doc.owner); } channel(doc.channels); }"

DocIds = dict[str, set[str]]


def _session_auth(form: str, session_id: str) -> dict[str, Any]:
    """
    The replication-entry fields that hand `session_id` to Edge Server in the given form.
    :param form: One of the `cookie_form` parameters of the bidirectional test
    :param session_id: The id of an SGW session
    """
    match form:
        case "bare":
            return {"auth": {"session_cookie": session_id}}
        case "prefixed":
            return {"auth": {"session_cookie": f"{COOKIE_NAME}={session_id}"}}
        case "with_unrelated_cookie_header":
            return {"auth": {"session_cookie": session_id}, "headers": {"Cookie": UNRELATED_COOKIE}}
    raise ValueError(f"Unknown session cookie form: {form}")


def _count(ids: DocIds) -> int:
    """The number of document ids across every collection in `ids`."""
    return sum(len(v) for v in ids.values())


@pytest.mark.min_edge_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestSessionCookie(CBLTestClass):
    async def _setup_sgw(self, cblpytest: CBLPyTest) -> None:
        """Create the SGW database and the session user"""
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]

        self.mark_test_step(
            "Create the SGW `travel` database: guest disabled, the `requireUser(doc.owner)` sync function, "
            "`travel.airlines` and `travel.hotels`"
        )
        server.create_bucket(BUCKET)
        server.create_collections(BUCKET, SCOPE, list(COLLECTIONS))
        config = DatabaseConfig(
            bucket=BUCKET,
            scopes={SCOPE: ScopeConfig(collections={c: {"sync": SYNC_FUNCTION} for c in COLLECTIONS})},
            guest={"disabled": True},
            num_index_replicas=0,
        )
        await cblpytest.sync_gateway_cluster.create_database(SG_DB, config)

        self.mark_test_step(
            f"Add SGW user `{SESSION_USER}` with access to `{SESSION_CHANNEL}` only, in both collections"
        )
        access = sync_gateway.create_collection_access_dict({f"{SCOPE}.{c}": [SESSION_CHANNEL] for c in COLLECTIONS})
        await sync_gateway.add_user(SG_DB, SESSION_USER, SESSION_USER_PASSWORD, access)

    async def _sgw_status_with_cookie(self, cblpytest: CBLPyTest, session_id: str | None) -> int:
        """
        The status SGW's public API answers `GET /{db}/` with when presented `session_id`, or no
        credentials at all when it is None.  This sends the same Cookie header Edge Server should
        put on the replication handshake.
        """
        sync_gateway = cblpytest.sync_gateways[0]
        headers = {"Cookie": f"{COOKIE_NAME}={session_id}"} if session_id is not None else {}
        async with (
            aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session,
            session.get(f"{sync_gateway.public_url}/{SG_DB}/", headers=headers) as resp,
        ):
            return resp.status

    async def _create_verified_session(self, cblpytest: CBLPyTest) -> str:
        """Create a session for the session user and prove SGW accepts it before Edge Server is involved."""
        session_id = await cblpytest.sync_gateways[0].create_session(SG_DB, SESSION_USER)
        assert session_id, "SGW returned an empty session id"
        status = await self._sgw_status_with_cookie(cblpytest, session_id)
        assert status == 200, f"SGW answered {status} to a session it just issued, before Edge Server was involved"
        return session_id

    async def _seed_sgw_docs(
        self, cblpytest: CBLPyTest, prefix: str, restricted: bool = False
    ) -> tuple[DocIds, DocIds]:
        """
        Write documents into every collection through CBS

        :param prefix: Prefix for every document id, unique per seeding
        :param restricted: Whether to also seed documents in a channel the session user cannot read
        :return: The ids the session user can read, and the ids it cannot, per collection
        """
        server = cblpytest.couchbase_servers[0]
        sync_gateway = cblpytest.sync_gateways[0]
        visible: DocIds = {}
        hidden: DocIds = {}
        for collection in COLLECTIONS:
            visible[collection] = {f"{prefix}_{collection}_visible_{i}" for i in range(VISIBLE_PER_COLLECTION)}
            hidden[collection] = (
                {f"{prefix}_{collection}_restricted_{i}" for i in range(RESTRICTED_PER_COLLECTION)}
                if restricted
                else set()
            )
            for doc_id, channel in [(d, SESSION_CHANNEL) for d in visible[collection]] + [
                (d, RESTRICTED_CHANNEL) for d in hidden[collection]
            ]:
                server.upsert_document(
                    BUCKET,
                    doc_id,
                    {"type": collection, "name": f"Session cookie QE {doc_id}", "channels": [channel]},
                    scope=SCOPE,
                    collection=collection,
                )

        for collection in COLLECTIONS:
            await sync_gateway.wait_for_documents(
                SG_DB, visible[collection] | hidden[collection], scope=SCOPE, collection=collection
            )

        return visible, hidden

    async def _write_es_config(self, cblpytest: CBLPyTest, tmp_path: Path, name: str, fields: dict[str, Any]) -> str:
        """
        Write an Edge Server config whose one replication authenticates with `fields` and nothing else.

        :param name: File stem, unique per config written in a test
        :param fields: The `auth` and/or `headers` entries of the replication
        :return: The path of the written config
        """
        config = await read_json_file(CONFIG_TEMPLATE)
        replication = config["replications"][0]
        replication["source"] = cblpytest.sync_gateways[0].replication_url(SG_DB)
        replication.pop("auth", None)
        replication.pop("headers", None)
        replication.update(fields)

        config_path = str(tmp_path / f"{name}.json")
        await write_json_file(config_path, config)
        return config_path

    async def _assert_docs_not_on_es(self, edge_server: EdgeServer, unexpected: DocIds, why: str) -> None:
        """Fail if any id in `unexpected` is on Edge Server."""
        present: DocIds = {}
        for collection in COLLECTIONS:
            response = await edge_server.get_all_documents(ES_DB, collection=f"{SCOPE}.{collection}")
            present[collection] = {row.id for row in response.rows}
        leaked = {c: sorted(ids & present[c]) for c, ids in unexpected.items() if ids & present[c]}
        assert not leaked, f"{why}: {leaked}"

    @pytest.mark.parametrize(
        "cookie_form",
        ["bare", "prefixed", "with_unrelated_cookie_header"],
    )
    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_cookie_bidirectional_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path, cookie_form: str
    ) -> None:
        sync_gateway = cblpytest.sync_gateways[0]
        prefix = f"bidi_{cookie_form}"

        await self._setup_sgw(cblpytest)

        self.mark_test_step(
            f"Seed {VISIBLE_PER_COLLECTION} `{SESSION_CHANNEL}` and {RESTRICTED_PER_COLLECTION} "
            f"`{RESTRICTED_CHANNEL}` documents into each collection through CBS, and wait for SGW to import them"
        )
        _, hidden = await self._seed_sgw_docs(cblpytest, prefix, restricted=True)

        self.mark_test_step("Create a session for `session_user` and verify SGW accepts it")
        session_id = await self._create_verified_session(cblpytest)

        self.mark_test_step(f"Configure ES with the session in `{cookie_form}` form and start it")
        config_path = await self._write_es_config(
            cblpytest, tmp_path, f"es_{cookie_form}", _session_auth(cookie_form, session_id)
        )
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=ES_DB, config_file=config_path)

        self.mark_test_step("Wait for the replicator to exist, report no error, and be `Idle`")
        await edge_server.wait_for_idle()

        self.mark_test_step(f"Verify none of the {_count(hidden)} `{RESTRICTED_CHANNEL}` documents are on ES")
        await self._assert_docs_not_on_es(
            edge_server, hidden, "Pulled documents the session user cannot read, so the session was not the identity"
        )

        self.mark_test_step("On ES, write `_foreign` owned by `other_user`, then `_owned` owned by `session_user`")
        foreign_id = f"{prefix}_foreign"
        owned_id = f"{prefix}_owned"
        await edge_server.put_document_with_id(
            {"type": "push", "owner": "other_user", "channels": [SESSION_CHANNEL]},
            foreign_id,
            ES_DB,
            collection=f"{SCOPE}.airlines",
        )
        for collection in COLLECTIONS:
            await edge_server.put_document_with_id(
                {"type": "push", "owner": SESSION_USER, "channels": [SESSION_CHANNEL]},
                owned_id,
                ES_DB,
                collection=f"{SCOPE}.{collection}",
            )

        self.mark_test_step("Wait for both `_owned` documents to reach SGW with `owner: session_user`")
        for collection in COLLECTIONS:
            await sync_gateway.wait_for_documents(SG_DB, [owned_id], scope=SCOPE, collection=collection)
            doc = await sync_gateway.get_document(SG_DB, owned_id, scope=SCOPE, collection=collection)
            assert doc.body.get("owner") == SESSION_USER, (
                f"{owned_id} in {SCOPE}.{collection} reached SGW without its owner: {doc}"
            )

        self.mark_test_step("Verify `_foreign` is not on SGW: the push was made as `session_user`")
        sgw_airlines = await sync_gateway.get_all_documents(SG_DB, scope=SCOPE, collection="airlines")
        assert foreign_id not in {row.id for row in sgw_airlines.rows}, (
            f"{foreign_id} was accepted by requireUser('other_user'), so the push did not authenticate as {SESSION_USER}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_cookie_across_restart_revoke_and_rotate(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path
    ) -> None:
        sync_gateway = cblpytest.sync_gateways[0]

        await self._setup_sgw(cblpytest)

        self.mark_test_step("Seed phase 1 documents through CBS and wait for SGW to import them")
        await self._seed_sgw_docs(cblpytest, "lifecycle_p1")

        self.mark_test_step("Create session A, verify SGW accepts it, and start ES with it")
        session_a = await self._create_verified_session(cblpytest)
        config_a = await self._write_es_config(cblpytest, tmp_path, "es_session_a", _session_auth("bare", session_a))
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=ES_DB, config_file=config_a)

        self.mark_test_step("Wait for the replicator to be `Idle` and verify the phase 1 documents are on ES")
        await edge_server.wait_for_idle()

        self.mark_test_step("Restart ES on the same config and database")
        await cblpytest.edge_servers[0].kill_server()
        edge_server = await cblpytest.edge_servers[0].start_server()

        self.mark_test_step("Seed phase 2 documents through CBS and wait for SGW to import them")
        await self._seed_sgw_docs(cblpytest, "lifecycle_p2")

        self.mark_test_step("Wait for the replicator to be `Idle` and verify the phase 2 documents are on ES")
        await edge_server.wait_for_idle()

        self.mark_test_step("Stop ES, revoke session A, and verify SGW rejects it")
        await cblpytest.edge_servers[0].kill_server()
        await sync_gateway.delete_session(SG_DB, session_a)
        status = await self._sgw_status_with_cookie(cblpytest, session_a)
        assert status == 401, f"SGW answered {status} to a revoked session"

        self.mark_test_step("Seed phase 3 documents through CBS and wait for SGW to import them")
        phase3, _ = await self._seed_sgw_docs(cblpytest, "lifecycle_p3")

        self.mark_test_step("Start ES on the same config and database")
        edge_server = await cblpytest.edge_servers[0].start_server()

        self.mark_test_step("Wait for ES to give up on the replicator with a 401")
        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.wait_for_idle()

        self.mark_test_step("Verify none of the phase 3 documents are on ES")
        await self._assert_docs_not_on_es(edge_server, phase3, "Replicated with a revoked session")

        self.mark_test_step("On ES, write `lifecycle_offline_write` while the replicator is down")
        offline_id = "lifecycle_offline_write"
        await edge_server.put_document_with_id(
            {"type": "push", "owner": SESSION_USER, "channels": [SESSION_CHANNEL]},
            offline_id,
            ES_DB,
            collection=f"{SCOPE}.airlines",
        )

        self.mark_test_step("Create session B, verify SGW accepts it, and restart ES with it")
        session_b = await self._create_verified_session(cblpytest)
        config_b = await self._write_es_config(cblpytest, tmp_path, "es_session_b", _session_auth("bare", session_b))
        await cblpytest.edge_servers[0].kill_server()
        edge_server = await cblpytest.edge_servers[0].start_server(config_b)

        self.mark_test_step("Wait for the replicator to be `Idle` and verify the phase 3 documents are on ES")
        await edge_server.wait_for_idle()

        self.mark_test_step("Wait for `lifecycle_offline_write` to reach SGW")
        await sync_gateway.wait_for_documents(SG_DB, [offline_id], scope=SCOPE, collection="airlines")

    @pytest.mark.parametrize("session_kind", ["expired", "never_issued"])
    @pytest.mark.asyncio(loop_scope="session")
    async def test_invalid_session_cookie_rejected(
        self, cblpytest: CBLPyTest, dataset_path: Path, tmp_path: Path, session_kind: str
    ) -> None:
        await self._setup_sgw(cblpytest)

        self.mark_test_step("Seed documents through CBS and wait for SGW to import them")
        seeded, _ = await self._seed_sgw_docs(cblpytest, f"invalid_{session_kind}")

        self.mark_test_step(f"Obtain an `{session_kind}` session")
        if session_kind == "expired":
            session_id = await cblpytest.sync_gateways[0].create_session(SG_DB, SESSION_USER, ttl=EXPIRED_SESSION_TTL)
            await asyncio.sleep(EXPIRED_SESSION_TTL * 2)
        else:
            session_id = secrets.token_hex(20)

        self.mark_test_step("Verify SGW rejects the session")
        status = await self._sgw_status_with_cookie(cblpytest, session_id)
        assert status == 401, f"SGW answered {status} to an {session_kind} session, so the test cannot prove anything"

        self.mark_test_step("Start ES with the session as a bare `auth.session_cookie`")
        config_path = await self._write_es_config(
            cblpytest, tmp_path, f"es_{session_kind}", _session_auth("bare", session_id)
        )
        edge_server = await cblpytest.edge_servers[0].configure_dataset(db_name=ES_DB, config_file=config_path)

        self.mark_test_step("Wait for ES to give up on the replicator with a 401")
        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.wait_for_idle()

        self.mark_test_step("Verify none of the seeded documents are on ES")
        await self._assert_docs_not_on_es(edge_server, seeded, f"Replicated with an {session_kind} session")
