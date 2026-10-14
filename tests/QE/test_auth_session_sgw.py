from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorAuthenticator,
    ReplicatorBearerAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorDocumentFlags,
    ReplicatorSessionAuthenticator,
    ReplicatorType,
    WaitForDocumentEventEntry,
)
from cbltest.api.syncgateway import DatabaseConfig, ScopeConfig, SyncGateway, get_sync_gateway_session_headers
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.plugins.sgw_cluster_manager import SyncGatewayClusterManager
from cbltest.responses import ServerVariant
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from shared.jwt_helper import generate_jwt, generate_rsa_keypair, local_jwt_provider, public_key_to_jwk

COLLECTION = "travel.airports"
# A real `travel` channel: user1 can see it, and the JWT database's user is scoped to it.
CHANNEL = "United States"
JWT_ISSUER = "https://qe.example.com"
JWT_AUDIENCE = "cbl-js-qe"
JWT_KID = "qe-test-key"
# SGW derives the username <issuer-host>_<sub> when the provider sets no user_prefix.
JWT_USERNAME = "qe.example.com_jwt-user"


def _mint_jwt(private_key: RSAPrivateKey, **overrides: Any) -> str:
    """Mints a JWT the `local_jwt` provider accepts, with any claim or header overridden."""
    claims: dict[str, Any] = {
        "subject": "jwt-user",
        "expires_in": 3600,
        "kid": JWT_KID,
        "issuer": JWT_ISSUER,
        "audience": JWT_AUDIENCE,
    }
    return generate_jwt(private_key, **(claims | overrides))


async def _create_jwt_database(cblpytest: CBLPyTest) -> RSAPrivateKey:
    """
    Creates an empty `travel` database with a `local_jwt` provider, and the user its tokens map to.

    The provider is part of the database's initial config, so Sync Gateway never has to reload the
    database to apply it.

    :return: The private key whose public half the provider trusts
    """
    private_key, public_key = generate_rsa_keypair()
    config = DatabaseConfig(
        bucket="travel",
        scopes={"travel": ScopeConfig(collections={"airports": {"sync": "function(doc){channel(doc.channels);}"}})},
        local_jwt={
            "qe": local_jwt_provider(
                [public_key_to_jwk(public_key, kid=JWT_KID)],
                issuer=JWT_ISSUER,
                audience=JWT_AUDIENCE,
                register=False,
            )
        },
    )
    await cblpytest.clusters[0].create_database("travel", config)
    sync_gateway = cblpytest.sync_gateways[0]
    access_dict = sync_gateway.create_collection_access_dict({COLLECTION: [CHANNEL]})
    await sync_gateway.add_user("travel", JWT_USERNAME, "pass", access_dict)
    return private_key


async def _assert_sg_rejects(sync_gateway: SyncGateway, headers: dict[str, str]) -> None:
    """Asserts SG answers 401 to a direct request made with the given credential headers."""
    async with sync_gateway.get_user_client(headers) as client:
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await client.get_all_documents("travel", "travel", "airports")
        assert exc_info.value.code == 401, f"Expected SG to answer 401, got {exc_info.value.code}"


async def _assert_auth_rejected(replicator: Replicator, sync_gateway: SyncGateway, headers: dict[str, str]) -> None:
    """
    Asserts the replicator stopped with an error, and that SG itself rejects the same credential.

    A browser gets no status from a refused WebSocket upgrade, so CBL JS can report -1 instead of
    401. On its own -1 could be any failure (a certificate mismatch, an unreachable SG), so the
    direct request shows it was the credential that SG refused.
    """
    status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
    assert status.error is not None, "Replicator stopped without an error; expected an auth rejection"
    assert status.error.code in (401, -1), (
        f"Expected 401 or -1, got ({status.error.domain} / {status.error.code}) {status.error.message}"
    )
    await _assert_sg_rejects(sync_gateway, headers)


@pytest.mark.cbl
@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
class TestSessionAuthReplication(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "replicator_type",
        [ReplicatorType.PUSH, ReplicatorType.PULL, ReplicatorType.PUSH_AND_PULL],
    )
    async def test_replicate_with_session_auth(
        self, cblpytest: CBLPyTest, dataset_path: Path, replicator_type: ReplicatorType
    ) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database and load `travel` dataset")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel"))[0]

        self.mark_test_step("Create a session for `user1`")
        session_id = await sync_gateway.create_session("travel", "user1")

        self.mark_test_step(f"""
            Start a replicator
            * endpoint: `/travel`
            * collections: `travel.airports`
            * type: {replicator_type}
            * continuous: false
            * credentials: session for `user1`
        """)
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=replicator_type,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=ReplicatorSessionAuthenticator(session_id),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops and check there is no error")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all documents are replicated correctly")
        await compare_local_and_remote(db, sync_gateway, replicator_type, "travel", [COLLECTION])

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_invalid_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database and load `travel` dataset")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel"))[0]

        self.mark_test_step("Start a pull replicator with a session ID Sync Gateway never issued")
        session_id = "d2VsbCB0aGF0J3Mgbm90IGEgc2Vzc2lvbg"
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=ReplicatorSessionAuthenticator(session_id),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Check the replicator stops with an auth error")
        await _assert_auth_rejected(replicator, sync_gateway, get_sync_gateway_session_headers(session_id))

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_concurrent_session_identities(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)

        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Create `alice` with access to `alice-only` and `bob` with access to `bob-only`")
        await sync_gateway.reset_user("names", "alice", "pass", ["alice-only"])
        await sync_gateway.reset_user("names", "bob", "pass", ["bob-only"])

        self.mark_test_step("Write `alice-doc` to `alice-only` and `bob-doc` to `bob-only` on SG")
        for doc_id, channel in (("alice-doc", "alice-only"), ("bob-doc", "bob-only")):
            await sync_gateway.create_document("names", doc_id, {"channels": [channel]}, wait_for_caching_feed=True)

        self.mark_test_step("Reset two empty local databases, `db_alice` and `db_bob`")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db_alice", "db_bob"])

        self.mark_test_step("Start a pull replicator per user, each on its own session, with no channel filter")
        replicators = [
            Replicator(
                db,
                sync_gateway.replication_url("names"),
                replicator_type=ReplicatorType.PULL,
                collections=[ReplicatorCollectionEntry(["_default._default"])],
                authenticator=ReplicatorSessionAuthenticator(await sync_gateway.create_session("names", user)),
                pinned_server_cert=sync_gateway.tls_cert(),
            )
            for db, user in zip(dbs, ("alice", "bob"), strict=True)
        ]
        for replicator in replicators:
            await replicator.start()

        self.mark_test_step("Wait until both replicators stop and check there is no error")
        for replicator in replicators:
            status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
            assert status.error is None, (
                f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
            )

        self.mark_test_step("Check `db_alice` holds only `alice-doc` and `db_bob` holds only `bob-doc`")
        for db, expected in zip(dbs, ("alice-doc", "bob-doc"), strict=True):
            docs = await db.get_all_documents("_default._default")
            ids = {d.id for d in docs["_default._default"]}
            assert ids == {expected}, f"Expected only {expected!r}, got {sorted(ids)}"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_bearer_token(self, cblpytest: CBLPyTest) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)

        self.mark_test_step("Create an empty SG `travel` database with a `local_jwt` provider and its user")
        sync_gateway = cblpytest.sync_gateways[0]
        private_key = await _create_jwt_database(cblpytest)

        self.mark_test_step("Reset local database with an empty `travel.airports` collection")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[COLLECTION]))[0]

        self.mark_test_step("Write `jwt-doc` on SG")
        await sync_gateway.create_document(
            "travel",
            "jwt-doc",
            {"channels": [CHANNEL]},
            scope="travel",
            collection="airports",
            wait_for_caching_feed=True,
        )

        self.mark_test_step("Start a pull replicator with a valid JWT")
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=ReplicatorBearerAuthenticator(_mint_jwt(private_key)),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops and check there is no error")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all documents are replicated correctly")
        await compare_local_and_remote(db, sync_gateway, ReplicatorType.PULL, "travel", [COLLECTION])

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param({"expires_in": -3600}, id="expired"),
            pytest.param({"issuer": "https://not-the-issuer.example.com"}, id="wrong-issuer"),
            pytest.param({"sign_with": generate_rsa_keypair()[0]}, id="bad-signature"),
            pytest.param({"alg": "none"}, id="unsigned"),
            pytest.param(None, id="not-a-jwt"),
        ],
    )
    async def test_replicate_with_bad_bearer_token(
        self, cblpytest: CBLPyTest, overrides: dict[str, Any] | None
    ) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)

        self.mark_test_step("Create an empty SG `travel` database with a `local_jwt` provider and its user")
        sync_gateway = cblpytest.sync_gateways[0]
        private_key = await _create_jwt_database(cblpytest)

        self.mark_test_step("Reset local database with an empty `travel.airports` collection")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[COLLECTION]))[0]

        self.mark_test_step("Start a pull replicator with a JWT that is wrong in exactly one way")
        token = "this.is.not-a-jwt" if overrides is None else _mint_jwt(private_key, **overrides)
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=ReplicatorBearerAuthenticator(token),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Check the replicator stops with an auth error")
        await _assert_auth_rejected(replicator, sync_gateway, {"Authorization": f"Bearer {token}"})

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_anonymous_replication_rejected(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Disable the GUEST user")
        await sync_gateway.add_user("travel", "GUEST", disabled=True)

        self.mark_test_step("Reset local database and load `travel` dataset")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel"))[0]

        self.mark_test_step("Start a pull replicator with no authenticator")
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=None,
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Check the replicator stops with an auth error")
        await _assert_auth_rejected(replicator, sync_gateway, {})

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_guest_replication_allowed(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Enable the GUEST user with access to the `United States` channel")
        await sync_gateway.add_user(
            "travel",
            "GUEST",
            collection_access=sync_gateway.create_collection_access_dict({COLLECTION: [CHANNEL]}),
            disabled=False,
        )

        self.mark_test_step("Reset local database and load `travel` dataset")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel"))[0]

        self.mark_test_step("""
            Start a replicator
            * endpoint: `/travel`
            * collections: `travel.airports`
            * type: pull
            * continuous: false
            * credentials: none
        """)
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=None,
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops and check there is no error")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check `db1` holds exactly the `travel.airports` documents SG serves to the GUEST user")
        async with sync_gateway.get_user_client({}) as guest:
            guest_ids = [row.id for row in (await guest.get_all_documents("travel", "travel", "airports")).rows]
        assert guest_ids, f"SG serves the GUEST user no documents in the `{CHANNEL}` channel"
        local_ids = {d.id for d in (await db.get_all_documents(COLLECTION))[COLLECTION]}
        assert local_ids == set(guest_ids), (
            f"Pulled {len(local_ids)} documents, but SG serves the GUEST user {len(guest_ids)}"
        )
        await compare_local_and_remote(db, sync_gateway, ReplicatorType.PULL, "travel", [COLLECTION], guest_ids)

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_revoked_during_continuous_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database and load `travel` dataset")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel"))[0]

        self.mark_test_step("Start a continuous push-and-pull replicator on a session for `user1`")
        session_id = await sync_gateway.create_session("travel", "user1")
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=ReplicatorSessionAuthenticator(session_id),
            pinned_server_cert=sync_gateway.tls_cert(),
            enable_document_listener=True,
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Delete the session and check SG rejects it for new requests")
        await sync_gateway.delete_session("travel", session_id)
        await _assert_sg_rejects(sync_gateway, get_sync_gateway_session_headers(session_id))

        self.mark_test_step("Write `post-revocation-doc` on SG")
        await sync_gateway.create_document(
            "travel", "post-revocation-doc", {"channels": [CHANNEL]}, scope="travel", collection="airports"
        )

        self.mark_test_step("Check the document arrives and the replicator stays idle")
        await replicator.wait_for_all_doc_events(
            {
                WaitForDocumentEventEntry(
                    COLLECTION, "post-revocation-doc", ReplicatorType.PULL, ReplicatorDocumentFlags.NONE
                )
            },
            max_retries=60,
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_jwt_user_revoked_during_continuous_replication(self, cblpytest: CBLPyTest) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)

        self.mark_test_step("Create an empty SG `travel` database with a `local_jwt` provider and its user")
        sync_gateway = cblpytest.sync_gateways[0]
        private_key = await _create_jwt_database(cblpytest)

        self.mark_test_step("Reset local database with an empty `travel.airports` collection")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[COLLECTION]))[0]

        self.mark_test_step("Start a continuous push-and-pull replicator with a valid JWT")
        token = _mint_jwt(private_key)
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=ReplicatorBearerAuthenticator(token),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Delete the user the JWT maps to and write `post-jwt-revocation-doc` on SG")
        await sync_gateway.delete_user("travel", JWT_USERNAME)
        await sync_gateway.create_document(
            "travel", "post-jwt-revocation-doc", {"channels": [CHANNEL]}, scope="travel", collection="airports"
        )

        self.mark_test_step("Check the replicator stops on an auth error and the document never arrives")
        await _assert_auth_rejected(replicator, sync_gateway, {"Authorization": f"Bearer {token}"})
        docs = await db.get_all_documents(COLLECTION)
        assert all(d.id != "post-jwt-revocation-doc" for d in docs[COLLECTION]), (
            "Document written after the JWT's user was deleted was still delivered"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_expired_jwt_then_fresh_token(self, cblpytest: CBLPyTest) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)

        self.mark_test_step("Create an empty SG `travel` database with a `local_jwt` provider and its user")
        sync_gateway = cblpytest.sync_gateways[0]
        private_key = await _create_jwt_database(cblpytest)

        self.mark_test_step("Reset local database with an empty `travel.airports` collection")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[COLLECTION]))[0]

        self.mark_test_step("Start a one-shot push-and-pull replicator with an expired JWT")
        expired_token = _mint_jwt(private_key, expires_in=-3600)
        expired = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=ReplicatorBearerAuthenticator(expired_token),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await expired.start()

        self.mark_test_step("Check the replicator stops with an auth error")
        await _assert_auth_rejected(expired, sync_gateway, {"Authorization": f"Bearer {expired_token}"})

        self.mark_test_step("Start a new continuous push-and-pull replicator with a fresh JWT")
        fresh = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=ReplicatorBearerAuthenticator(_mint_jwt(private_key)),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await fresh.start()

        self.mark_test_step("Wait until the replicator is idle and check there is no error")
        status = await fresh.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("auth_type", ["session", "jwt"])
    @pytest.mark.skip(reason="https://jira.issues.couchbase.com/browse/CBL-9117")
    async def test_sgw_restart_during_replication(
        self,
        cblpytest: CBLPyTest,
        dataset_path: Path,
        sg_cluster_manager: SyncGatewayClusterManager,
        auth_type: str,
    ) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)
        self.skip_if_not(
            sg_cluster_manager.has_shell2http_sidecar,
            "shell2http sidecar is not reachable on every Sync Gateway host",
        )

        self.mark_test_step(f"Create the SG `travel` database and {auth_type} credentials")
        sync_gateway = cblpytest.sync_gateways[0]
        authenticator: ReplicatorAuthenticator
        if auth_type == "session":
            await cblpytest.clusters[0].configure_dataset(dataset_path, "travel")
            authenticator = ReplicatorSessionAuthenticator(await sync_gateway.create_session("travel", "user1"))
        else:
            authenticator = ReplicatorBearerAuthenticator(_mint_jwt(await _create_jwt_database(cblpytest)))

        self.mark_test_step("Reset local database with an empty `travel.airports` collection")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], collections=[COLLECTION]))[0]

        self.mark_test_step("Start a continuous push-and-pull replicator and wait until it is idle")
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=authenticator,
            pinned_server_cert=sync_gateway.tls_cert(),
            enable_document_listener=True,
        )
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Stop SG and wait until the replicator is offline")
        await sg_cluster_manager.nodes[0].stop()
        await replicator.wait_for(ReplicatorActivityLevel.OFFLINE)

        self.mark_test_step(f"Start SG and write `post-restart-{auth_type}` on it")
        await sg_cluster_manager.nodes[0].start()
        doc_id = f"post-restart-{auth_type}"
        await sync_gateway.create_document(
            "travel", doc_id, {"channels": [CHANNEL]}, scope="travel", collection="airports"
        )

        self.mark_test_step("Check the replicator reconnects on the same credentials and the document arrives")
        await replicator.wait_for_all_doc_events(
            {WaitForDocumentEventEntry(COLLECTION, doc_id, ReplicatorType.PULL, ReplicatorDocumentFlags.NONE)},
            max_retries=60,
            idle_timeout=timedelta(seconds=60),
        )

        await cblpytest.test_servers[0].cleanup()
