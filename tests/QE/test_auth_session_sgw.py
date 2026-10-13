import asyncio
from pathlib import Path
from typing import Any

import pytest
import tenacity
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import Database
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorAuthenticator,
    ReplicatorBearerAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorSessionAuthenticator,
    ReplicatorType,
)
from cbltest.api.syncgateway import DatabaseConfig, LocalJWT, get_sync_gateway_session_headers
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.plugins.sgw_cluster_manager import SyncGatewayClusterManager
from cbltest.responses import ServerVariant
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from shared.jwt_helper import generate_jwt, generate_rsa_keypair, public_key_to_jwk

COLLECTION = "travel.airports"
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


async def _configure_local_jwt(cblpytest: CBLPyTest) -> RSAPrivateKey:
    """
    Adds a `local_jwt` provider to the `travel` database and creates the user its tokens map to.

    :return: The private key whose public half the provider trusts
    """
    private_key, public_key = generate_rsa_keypair()
    provider = LocalJWT(
        issuer=JWT_ISSUER,
        client_id=JWT_AUDIENCE,
        register=False,
        algorithms=["RS256"],
        keys=[public_key_to_jwk(public_key, kid=JWT_KID)],
    )
    await cblpytest.sync_gateway_cluster.update_database_config("travel", DatabaseConfig(local_jwt={"qe": provider}))
    await cblpytest.sync_gateways[0].add_user(
        "travel",
        JWT_USERNAME,
        password="pass",
        collection_access={"travel": {"airports": {"admin_channels": ["*"]}}},
    )
    return private_key


async def _assert_auth_rejected(replicator: Replicator) -> None:
    """
    Asserts the replicator stopped on an auth error. A browser gets no status from a refused
    WebSocket upgrade, so CBL JS reports -1 there instead of 401.
    """
    status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
    assert status.error is not None, "Replicator stopped without an error; expected an auth rejection"
    assert status.error.code in (401, -1), (
        f"Expected 401 or -1, got ({status.error.domain} / {status.error.code}) {status.error.message}"
    )


async def _wait_for_local_doc(db: Database, doc_id: str, timeout: int = 30) -> bool:
    """Polls the local `travel.airports` collection once a second and returns whether `doc_id` arrived."""
    for _ in range(timeout):
        docs = await db.get_all_documents(COLLECTION)
        if any(d.id == doc_id for d in docs[COLLECTION]):
            return True
        await asyncio.sleep(1)
    return False


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
        await self.skip_if_sgw_not(cblpytest.sync_gateways[0], "=4.2.0")

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
        await self.skip_if_sgw_not(cblpytest.sync_gateways[0], "=4.2.0")

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database and load `travel` dataset")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel"))[0]

        self.mark_test_step("Start a pull replicator with a session ID Sync Gateway never issued")
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=ReplicatorSessionAuthenticator("d2VsbCB0aGF0J3Mgbm90IGEgc2Vzc2lvbg"),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Check the replicator stops with an auth error")
        await _assert_auth_rejected(replicator)

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_concurrent_session_identities(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)
        await self.skip_if_sgw_not(cblpytest.sync_gateways[0], "=4.2.0")

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
    async def test_replicate_with_bearer_token(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)
        await self.skip_if_sgw_not(cblpytest.sync_gateways[0], "=4.2.0")

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Configure a `local_jwt` provider and create the user its tokens map to")
        private_key = await _configure_local_jwt(cblpytest)

        self.mark_test_step("Reset local database and load `travel` dataset")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel"))[0]

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
        self, cblpytest: CBLPyTest, dataset_path: Path, overrides: dict[str, Any] | None
    ) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)
        await self.skip_if_sgw_not(cblpytest.sync_gateways[0], "=4.2.0")

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Configure a `local_jwt` provider and create the user its tokens map to")
        private_key = await _configure_local_jwt(cblpytest)

        self.mark_test_step("Reset local database and load `travel` dataset")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel"))[0]

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
        await _assert_auth_rejected(replicator)

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_anonymous_replication_rejected(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)
        await self.skip_if_sgw_not(cblpytest.sync_gateways[0], "=4.2.0")

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
        await _assert_auth_rejected(replicator)

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_guest_replication_allowed(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)
        await self.skip_if_sgw_not(cblpytest.sync_gateways[0], "=4.2.0")

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Enable the GUEST user with access to `travel.airports`")
        await sync_gateway.add_user(
            "travel",
            "GUEST",
            collection_access={"travel": {"airports": {"admin_channels": ["*"]}}},
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

        self.mark_test_step("Check that all documents are replicated correctly")
        await compare_local_and_remote(db, sync_gateway, ReplicatorType.PULL, "travel", [COLLECTION])

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_revoked_during_continuous_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)
        await self.skip_if_sgw_not(cblpytest.sync_gateways[0], "=4.2.0")

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
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is idle")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Delete the session and check SG rejects it for new requests")
        await sync_gateway.delete_session("travel", session_id)
        async with sync_gateway.get_user_client(get_sync_gateway_session_headers(session_id)) as client:
            with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
                await client.get_all_documents("travel", "travel", "airports")
            assert exc_info.value.code == 401, f"Expected 401 for a deleted session, got {exc_info.value.code}"

        self.mark_test_step("Write `post-revocation-doc` on SG 15 seconds later")
        await asyncio.sleep(15)
        await sync_gateway.create_document(
            "travel", "post-revocation-doc", {"channels": ["*"]}, scope="travel", collection="airports"
        )

        self.mark_test_step("Check the document arrives and the replicator stays idle")
        assert await _wait_for_local_doc(db, "post-revocation-doc"), (
            "Document written after the session was deleted never arrived; SG authenticates at connect "
            "time, so the established replication should have continued"
        )
        status = await replicator.get_status()
        assert status.activity == ReplicatorActivityLevel.IDLE, f"Replicator left IDLE ({status.activity})"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_jwt_user_revoked_during_continuous_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)
        await self.skip_if_sgw_not(cblpytest.sync_gateways[0], "=4.2.0")

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Configure a `local_jwt` provider and create the user its tokens map to")
        private_key = await _configure_local_jwt(cblpytest)

        self.mark_test_step("Reset local database and load `travel` dataset")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel"))[0]

        self.mark_test_step("Start a continuous push-and-pull replicator with a valid JWT")
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=ReplicatorBearerAuthenticator(_mint_jwt(private_key)),
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
            "travel", "post-jwt-revocation-doc", {"channels": ["*"]}, scope="travel", collection="airports"
        )

        self.mark_test_step("Check the document never reaches the deleted user")
        assert not await _wait_for_local_doc(db, "post-jwt-revocation-doc"), (
            "Document written after the JWT's user was deleted was still delivered"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_expired_jwt_then_fresh_token(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)
        await self.skip_if_sgw_not(cblpytest.sync_gateways[0], "=4.2.0")

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Configure a `local_jwt` provider and create the user its tokens map to")
        private_key = await _configure_local_jwt(cblpytest)

        self.mark_test_step("Reset local database and load `travel` dataset")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel"))[0]

        self.mark_test_step("Start a continuous push-and-pull replicator with an expired JWT")
        expired = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=ReplicatorBearerAuthenticator(_mint_jwt(private_key, expires_in=-3600)),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await expired.start()

        self.mark_test_step("Check the replicator stops with an auth error")
        await _assert_auth_rejected(expired)

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
    async def test_sgw_restart_during_replication(
        self,
        cblpytest: CBLPyTest,
        dataset_path: Path,
        sg_cluster_manager: SyncGatewayClusterManager,
        auth_type: str,
    ) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.JS)
        await self.skip_if_sgw_not(cblpytest.sync_gateways[0], "=4.2.0")

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step(f"Create {auth_type} credentials")
        authenticator: ReplicatorAuthenticator
        if auth_type == "session":
            authenticator = ReplicatorSessionAuthenticator(await sync_gateway.create_session("travel", "user1"))
        else:
            authenticator = ReplicatorBearerAuthenticator(_mint_jwt(await _configure_local_jwt(cblpytest)))

        self.mark_test_step("Reset local database and load `travel` dataset")
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel"))[0]

        self.mark_test_step("Start a continuous push-and-pull replicator and wait until it is idle")
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry([COLLECTION])],
            authenticator=authenticator,
            pinned_server_cert=sync_gateway.tls_cert(),
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
        await sync_gateway.create_document("travel", doc_id, {"channels": ["*"]}, scope="travel", collection="airports")

        self.mark_test_step("Check the replicator reconnects on the same credentials and the document arrives")
        assert await _wait_for_local_doc(db, doc_id, timeout=60), (
            f"Document never arrived after the restart; replicator is {(await replicator.get_status()).activity}"
        )

        await cblpytest.test_servers[0].cleanup()
