import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import Database
from cbltest.api.error import (
    CblSyncGatewayBadResponseError,
    CblTestServerBadResponseError,
)
from cbltest.api.error_types import ErrorDomain
from cbltest.api.replicator import (
    Replicator,
    ReplicatorActivityLevel,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.replicator_types import (
    ReplicatorAuthenticator,
    ReplicatorBasicAuthenticator,
    ReplicatorBearerAuthenticator,
    ReplicatorSessionAuthenticator,
)
from cbltest.api.syncgateway import LocalJWT, SyncGateway, SyncGatewayUserClient
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.logging import cbl_warning
from cbltest.responses import ServerVariant
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from shared.jwt_helper import generate_jwt, generate_rsa_keypair, public_key_to_jwk

_JWT_ISSUER = "https://qe.example.com"
_JWT_AUDIENCE = "cbl-js-qe"
_JWT_KID = "qe-test-key"
_JWT_SUBJECT = "jwt-user"
# SGW derives <issuer-host>_<sub> when a provider has no explicit user_prefix.
_JWT_USERNAME = "qe.example.com_jwt-user"


def _fmt_error(error: Any) -> str:
    """
    Renders an ErrorResponseBody usefully.

    It has no __str__, so interpolating it directly yields a memory address --
    which tells you a replication failed but not why.
    """
    if error is None:
        return "None"
    return f"{getattr(error, 'domain', '?')}/{getattr(error, 'code', '?')}: {getattr(error, 'message', '')}"


def _mint_bad_jwt(private_key: Any, mutation: str) -> str:
    """
    Mints a JWT that is wrong in exactly one way.

    Each mutation changes a single claim or header so that a rejection is attributable:
    if the `wrong audience` case passes but `wrong issuer` fails, the provider is
    checking one and not the other.
    """
    kwargs: dict[str, Any] = {
        "subject": "jwt-user",
        "expires_in": 3600,
        "kid": _JWT_KID,
        "issuer": _JWT_ISSUER,
        "audience": _JWT_AUDIENCE,
    }
    match mutation:
        case "expired":
            kwargs["expires_in"] = -3600
        case "issuer":
            kwargs["issuer"] = "https://not-the-issuer.example.com"
        case "audience":
            kwargs["audience"] = "some-other-client"
        case "kid":
            kwargs["kid"] = "a-key-nobody-published"
        case "signature":
            # Sign with a key whose public half was never given to Sync Gateway.
            other_key, _ = generate_rsa_keypair()
            kwargs["sign_with"] = other_key
        case "alg_none":
            kwargs["alg"] = "none"
        case "malformed":
            return "this.is.not-a-jwt"
        case _:
            raise ValueError(f"Unknown JWT mutation {mutation!r}")
    return generate_jwt(private_key, **kwargs)


async def _assert_session_rejected(client: SyncGatewayUserClient, db_name: str) -> None:
    """
    Asserts that a session no longer identifies its user.

    ``GET /{db}/_session`` is an introspection endpoint, not an authorization gate:
    for an invalid, revoked or absent session Sync Gateway answers 200 with
    ``userCtx.name`` null rather than 401.  It tells you who you are, and "nobody" is
    a valid answer.  Both outcomes mean rejected, so accept either -- but never a 200
    that still names a user, which is the thing these tests exist to catch.
    """
    try:
        ctx = await client.get_session(db_name)
    except CblSyncGatewayBadResponseError as e:
        assert e.code == 401, f"Expected 401 or an anonymous session, got {e.code}"
        return

    name = ctx.get("userCtx", {}).get("name")
    assert name is None, f"Session still resolves to {name!r}; it was not rejected"


async def _assert_auth_rejected(cblpytest: CBLPyTest, replicator: Replicator) -> None:
    """
    Asserts that a replicator stopped because Sync Gateway rejected its credentials.

    The JS test server surfaces the raw HTTP status where the native platforms surface
    the CBL-mapped code, so the assertion has to fork on variant -- same shape as
    test_basic_replication.py::test_replicate_non_existing_sg_collections.

    Note this asserts STOPPED rather than OFFLINE: an auth rejection is terminal, and a
    replicator that sits in OFFLINE retrying a credential that will never work is itself
    the bug these tests are looking for.
    """
    status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
    assert status.error is not None, "Replicator stopped without an error; expected a 401"
    if (await cblpytest.test_servers[0].get_info()).variant == ServerVariant.JS:
        # A browser gets no status from a refused WebSocket upgrade, so a SESSION
        # rejection surfaces as WebSocketError/-1 rather than 401. Basic auth does
        # produce a readable 401, because it fails on the _session fetch first.
        # Accept either, but require that the replicator stopped with an error --
        # sitting in OFFLINE retrying a dead credential is still a failure.
        assert status.error.code in (401, -1), f"Expected 401 or -1, got {(status.error)}"
    else:
        assert status.error.code == 10401 and ErrorDomain.equal(status.error.domain, ErrorDomain.CBL), (
            f"Expected CBL/10401, got {(status.error)}"
        )


@pytest.mark.min_sync_gateways(1)
class TestSessionSyncGateway(CBLTestClass):
    """
    Sync Gateway's session API, exercised directly.

    Deliberately carries no ``min_test_servers`` marker: nothing here touches a
    replicator, so these run in any topology with a Sync Gateway and catch session
    regressions even while the JS SDK's session support is still landing.  The
    replication half of the suite lives in :class:`TestSessionAuthReplication`.
    """

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_dies_with_user(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """SESS-14: deleting a user invalidates the sessions issued to them."""
        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "names")
        await sync_gateway.reset_user("names", "test", "pass", ["*"])

        self.mark_test_step("Create a session for `test`")
        session = await sync_gateway.create_session("names", "test")
        client = SyncGatewayUserClient.from_session(sync_gateway.hostname, session, secure=sync_gateway.secure)
        try:
            self.mark_test_step("Delete the user")
            await sync_gateway.delete_user("names", "test")

            self.mark_test_step("Check the orphaned session is rejected")
            await _assert_session_rejected(client, "names")
        finally:
            await client.close()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_revocation(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """SESS-09/10: sessions can be revoked individually and per user."""
        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "names")
        await sync_gateway.reset_user("names", "user1", "pass", ["*"])

        self.mark_test_step("Create three sessions for `user1`")
        sessions = [await sync_gateway.create_session("names", "user1") for _ in range(3)]
        ids = {s.session_id for s in sessions}
        assert len(ids) == 3, "Sync Gateway reused a session ID across separate creations"

        self.mark_test_step("Revoke the first session by ID and check the others survive")
        await sync_gateway.delete_session("names", sessions[0].session_id)

        clients = [
            SyncGatewayUserClient.from_session(sync_gateway.hostname, s, secure=sync_gateway.secure) for s in sessions
        ]
        try:
            await _assert_session_rejected(clients[0], "names")
            for client in clients[1:]:
                ctx = await client.get_session("names")
                assert ctx.get("userCtx", {}).get("name") == "user1", (
                    "Revoking one session appears to have invalidated the others"
                )

            self.mark_test_step("Revoke all remaining sessions for `user1`")
            await sync_gateway.delete_user_sessions("names", "user1")

            self.mark_test_step("Check every session is now rejected")
            for client in clients:
                await _assert_session_rejected(client, "names")
        finally:
            for client in clients:
                await client.close()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_is_database_scoped(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """SESS-13: a session minted for one database is not valid on another."""
        self.mark_test_step("Reset SG and load `names` and `travel` datasets")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "names")
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Create a session against `names`")
        async with sync_gateway.session_for("names", "user1") as session:
            client = SyncGatewayUserClient.from_session(sync_gateway.hostname, session, secure=sync_gateway.secure)
            try:
                self.mark_test_step("Check the session is accepted by `names`")
                ctx = await client.get_session("names")
                assert ctx.get("userCtx", {}).get("name") == "user1"

                self.mark_test_step("Check the same session is rejected by `travel`")
                await _assert_session_rejected(client, "travel")
            finally:
                await client.close()


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
class TestSessionAuthReplication(CBLTestClass):
    """
    Session authentication on the CBL replicator.

    Written against CBL JS, but the assertions fork on server variant so this runs
    unchanged on the native platforms.
    """

    # ---------------------------------------------------------------- SREP-01..14

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "replicator_type",
        [ReplicatorType.PUSH, ReplicatorType.PULL, ReplicatorType.PUSH_AND_PULL],
    )
    async def test_replicate_with_session_auth(
        self, cblpytest: CBLPyTest, dataset_path: Path, replicator_type: ReplicatorType
    ) -> None:
        """SREP-01/02/03: one-shot replication succeeds on a session token."""
        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")
        db = dbs[0]

        self.mark_test_step("Create a session for `user1`")
        async with sync_gateway.session_for("travel", "user1") as session:
            self.mark_test_step(f"""
                Start a replicator
                * endpoint: `/travel`
                * collections: `travel.airlines`
                * type: {replicator_type}
                * continuous: false
                * credentials: session token for user1
            """)
            replicator = Replicator(
                db,
                sync_gateway.replication_url("travel"),
                replicator_type=replicator_type,
                collections=[ReplicatorCollectionEntry(["travel.airlines"])],
                authenticator=ReplicatorSessionAuthenticator(session.session_id, session.cookie_name),
                pinned_server_cert=sync_gateway.tls_cert(),
            )
            await replicator.start()

            self.mark_test_step("Wait until the replicator stops and check there is no error")
            status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
            assert status.error is None, f"Session-authenticated replication failed: {status.error}"

            self.mark_test_step("Check that all documents are replicated correctly")
            await compare_local_and_remote(
                db,
                sync_gateway,
                replicator_type,
                "travel",
                ["travel.airlines"],
            )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_invalid_session(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        SREP-05: a well-formed but unissued session token is rejected with a 401.

        The token below is valid as an HTTP token -- it is a shape Sync Gateway will
        actually look up and reject, rather than one the SDK refuses locally.  See
        test_replicate_with_malformed_session for the local-validation case.
        """
        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")

        self.mark_test_step("Start a replicator with a session token that was never issued")
        replicator = Replicator(
            dbs[0],
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorSessionAuthenticator("d2VsbCB0aGF0J3Mgbm90IGEgc2Vzc2lvbg"),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Check the replicator stops with a 401 rather than retrying")
        await _assert_auth_rejected(cblpytest, replicator)

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        ("label", "session_id"),
        [
            ("comma", "bad,id"),
            ("whitespace", "bad id"),
            ("slash", "bad/id"),
            ("empty", ""),
        ],
    )
    async def test_replicate_with_malformed_session(
        self, cblpytest: CBLPyTest, dataset_path: Path, label: str, session_id: str
    ) -> None:
        """
        SREP-05a: a session ID that is not a legal WebSocket token is rejected locally.

        CBL JS validates the token shape before making any network call and fails with
        400 rather than 401.  That distinction is worth asserting: a 401 here would mean
        the malformed token was sent to Sync Gateway, and an unauthenticated request that
        looks like an auth failure is exactly the ambiguity these tests exist to remove.
        """
        if (await cblpytest.test_servers[0].get_info()).variant != ServerVariant.JS:
            self.skip("Local session-ID validation is a CBL JS behaviour")
            return

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")

        self.mark_test_step(f"Start a replicator with a session ID containing a {label}")
        replicator = Replicator(
            dbs[0],
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorSessionAuthenticator(session_id),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Check the replicator fails validation with 400, not 401")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is not None, "Replicator accepted a malformed session ID"
        assert status.error.code == 400, (
            f"Expected 400 from local validation, got {status.error.code}; "
            "a 401 would mean the malformed token was sent to Sync Gateway"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_custom_cookie_name_unsupported(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        SREP-10: CBL JS rejects a custom session cookie name with 501.

        The cross-platform TDK spec has a `cookieName` field because the native platforms
        implement SESSION as a `Cookie` header.  A browser cannot set that header on a
        WebSocket handshake, so CBL JS puts the session ID on the handshake subprotocol
        and has no cookie to name.  The test server therefore refuses rather than
        silently ignoring the field -- otherwise a test asserting on a custom cookie name
        would pass without the name ever being honoured.
        """
        if (await cblpytest.test_servers[0].get_info()).variant != ServerVariant.JS:
            self.skip("Custom cookie names are supported on the native platforms")
            return

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")

        self.mark_test_step("Create a valid session, then pair it with a custom cookie name")
        async with sync_gateway.session_for("travel", "user1") as session:
            replicator = Replicator(
                dbs[0],
                sync_gateway.replication_url("travel"),
                replicator_type=ReplicatorType.PULL,
                collections=[ReplicatorCollectionEntry(["travel.airlines"])],
                authenticator=ReplicatorSessionAuthenticator(session.session_id, "MyAppSession"),
                pinned_server_cert=sync_gateway.tls_cert(),
            )

            self.mark_test_step("Check the test server refuses with 501")
            with pytest.raises(CblTestServerBadResponseError) as excinfo:
                await replicator.start()
            assert excinfo.value.code == 501, f"Expected 501, got {excinfo.value.code}"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_concurrent_session_identities(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        SREP-14: two sessions with disjoint channels replicate against the same endpoint
        without leaking each other's documents.

        This is the test that would catch a session token being cached or shared at the
        SDK or transport layer -- a plausible failure mode in a browser, where there is
        one cookie jar per origin.
        """
        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Create two users with disjoint channel access")
        await sync_gateway.reset_user("names", "alice", "pass", ["alice-only"])
        await sync_gateway.reset_user("names", "bob", "pass", ["bob-only"])

        self.mark_test_step("Reset two local databases")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db_alice", "db_bob"], dataset="names")

        async with (
            sync_gateway.session_for("names", "alice") as alice_session,
            sync_gateway.session_for("names", "bob") as bob_session,
        ):
            self.mark_test_step("Start both replicators against the same endpoint at once")
            replicators = []
            for db, session, channel in (
                (dbs[0], alice_session, "alice-only"),
                (dbs[1], bob_session, "bob-only"),
            ):
                replicator = Replicator(
                    db,
                    sync_gateway.replication_url("names"),
                    replicator_type=ReplicatorType.PULL,
                    collections=[ReplicatorCollectionEntry(["_default._default"], channels=[channel])],
                    authenticator=ReplicatorSessionAuthenticator(session.session_id, session.cookie_name),
                    pinned_server_cert=sync_gateway.tls_cert(),
                )
                await replicator.start()
                replicators.append(replicator)

            self.mark_test_step("Check both replicators finish without an auth error")
            for replicator in replicators:
                status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
                assert status.error is None, f"Concurrent session replication failed: {status.error}"

        await cblpytest.test_servers[0].cleanup()

    # ---------------------------------------------------------------- BEARER / cookie / anonymous

    @pytest.mark.asyncio(loop_scope="session")
    async def test_replicate_with_bearer_token(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        OREP-01: replication succeeds on a bearer token validated by a `local_jwt` provider.

        Uses `local_jwt` rather than a full `oidc` provider so no external identity
        provider is needed in the topology -- the keypair is minted in-process by
        jwt_helper and its public JWK handed to Sync Gateway.
        """
        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Mint an RSA keypair and configure SG with a `local_jwt` provider")
        private_key, public_key = generate_rsa_keypair()
        jwk = public_key_to_jwk(public_key, kid=_JWT_KID)
        config = await sync_gateway.get_database_config("travel")
        config.local_jwt = {
            "qe": LocalJWT(
                issuer=_JWT_ISSUER,
                client_id=_JWT_AUDIENCE,
                register=False,
                algorithms=["RS256"],
                keys=[jwk],
            )
        }
        await sync_gateway.update_database_config("travel", config)

        self.mark_test_step("Create the user the token's `sub` claim maps to")
        await sync_gateway.delete_user("travel", "qe.example.com_jwt-user")
        await sync_gateway.add_user(
            "travel",
            # SGW derives the username as <issuer-host>_<sub> when a provider has no
            # explicit user_prefix, so the account must exist under that name, not the
            # bare sub claim. See OIDC-12.
            "qe.example.com_jwt-user",
            password="pass",
            collection_access={"travel": {"airlines": {"admin_channels": ["*"]}}},
        )

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")

        self.mark_test_step("Start a replicator authenticated with the bearer token")
        token = generate_jwt(
            private_key,
            subject="jwt-user",
            expires_in=3600,
            kid=_JWT_KID,
            issuer=_JWT_ISSUER,
            audience=_JWT_AUDIENCE,
        )
        replicator = Replicator(
            dbs[0],
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorBearerAuthenticator(token),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops and check there is no error")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Bearer-authenticated replication failed: {status.error}"

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        ("label", "mutation"),
        [
            ("expired", "expired"),
            ("wrong issuer", "issuer"),
            ("wrong audience", "audience"),
            ("bad signature", "signature"),
            ("unknown kid", "kid"),
            ("unsigned", "alg_none"),
            ("not a jwt", "malformed"),
        ],
    )
    async def test_replicate_with_bad_bearer_token(
        self, cblpytest: CBLPyTest, dataset_path: Path, label: str, mutation: str
    ) -> None:
        """OREP-02..07: every way a JWT can be wrong is rejected with a 401."""
        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Configure SG with a `local_jwt` provider")
        private_key, public_key = generate_rsa_keypair()
        jwk = public_key_to_jwk(public_key, kid=_JWT_KID)
        config = await sync_gateway.get_database_config("travel")
        config.local_jwt = {
            "qe": LocalJWT(
                issuer=_JWT_ISSUER,
                client_id=_JWT_AUDIENCE,
                register=False,
                algorithms=["RS256"],
                keys=[jwk],
            )
        }
        await sync_gateway.update_database_config("travel", config)
        await sync_gateway.delete_user("travel", "qe.example.com_jwt-user")
        await sync_gateway.add_user(
            "travel",
            # SGW derives the username as <issuer-host>_<sub> when a provider has no
            # explicit user_prefix, so the account must exist under that name, not the
            # bare sub claim. See OIDC-12.
            "qe.example.com_jwt-user",
            password="pass",
            collection_access={"travel": {"airlines": {"admin_channels": ["*"]}}},
        )

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")

        self.mark_test_step(f"Mint a token that is {label}")
        token = _mint_bad_jwt(private_key, mutation)

        self.mark_test_step("Start a replicator with the bad token and check it is rejected")
        replicator = Replicator(
            dbs[0],
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorBearerAuthenticator(token),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()
        await _assert_auth_rejected(cblpytest, replicator)

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_anonymous_replication_rejected(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        SREP-09: no authenticator against a guest-disabled database is rejected.

        Note this is not quite the same as proving the connection was anonymous: in a
        browser, an existing session cookie on the origin can still ride along even with
        no credentials configured.  What this asserts is the outcome that matters -- a
        database requiring auth does not sync without it.
        """
        self.mark_test_step("Reset SG and load `travel` dataset with guest disabled")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")
        config = await sync_gateway.get_database_config("travel")
        config.guest = {"disabled": True}
        await sync_gateway.put_database("travel", config)

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")

        self.mark_test_step("Start a replicator with no authenticator")
        replicator = Replicator(
            dbs[0],
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=None,
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()
        await _assert_auth_rejected(cblpytest, replicator)

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_half_empty_basic_credentials_rejected(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        Guards the legacy cookie-mode boundary.

        Only fully-empty Basic credentials select cookie mode; a half-empty credential
        still sends a literal `Authorization: Basic` header with a blank half.  The test
        server rejects the half-empty case with 400 so that a test cannot think it is
        exercising the cookie path when it is not.
        """
        if (await cblpytest.test_servers[0].get_info()).variant != ServerVariant.JS:
            self.skip("Cookie mode is a CBL JS behaviour")
            return

        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")

        for username, password in (("user1", ""), ("", "pass")):
            self.mark_test_step(f"Start a replicator with half-empty credentials ({username!r}, ...)")
            replicator = Replicator(
                dbs[0],
                sync_gateway.replication_url("travel"),
                replicator_type=ReplicatorType.PULL,
                collections=[ReplicatorCollectionEntry(["travel.airlines"])],
                authenticator=ReplicatorBasicAuthenticator(username, password),
                pinned_server_cert=sync_gateway.tls_cert(),
            )
            with pytest.raises(CblTestServerBadResponseError) as excinfo:
                await replicator.start()
            assert excinfo.value.code == 400, f"Expected 400, got {excinfo.value.code}"

        await cblpytest.test_servers[0].cleanup()

    # ---------------------------------------------------------------- mid-replication credential events

    async def _configure_local_jwt(self, sync_gateway: SyncGateway, db_name: str) -> RSAPrivateKey:
        """
        Adds a `local_jwt` provider to an existing database and creates the mapped user.

        Sync Gateway derives the username as `<issuer-host>_<sub>` when a provider has no
        explicit user_prefix, so the account must exist under that derived name rather
        than the bare `sub` claim -- see OIDC-12.
        """
        private_key, public_key = generate_rsa_keypair()
        config = await sync_gateway.get_database_config(db_name)
        config.local_jwt = {
            "qe": LocalJWT(
                issuer=_JWT_ISSUER,
                client_id=_JWT_AUDIENCE,
                register=False,
                algorithms=["RS256"],
                keys=[public_key_to_jwk(public_key, kid=_JWT_KID)],
            )
        }
        await sync_gateway.update_database_config(db_name, config)

        await sync_gateway.delete_user(db_name, _JWT_USERNAME)
        await sync_gateway.add_user(
            db_name,
            _JWT_USERNAME,
            password="pass",
            collection_access={"travel": {"airlines": {"admin_channels": ["*"]}}},
        )
        return private_key

    async def _classify_post_revocation_behaviour(
        self,
        replicator: Replicator,
        db: Database,
        collection: str,
        doc_id: str,
        timeout: int = 30,
    ) -> str:
        """
        Determines what a continuous replicator does after its credential is revoked.

        Replicator state alone is not enough to judge this.  A connection that stays
        IDLE but moves no data is defensible -- BLIP connections are long-lived and
        Sync Gateway authenticates at connect time -- whereas one that keeps delivering
        documents on a revoked credential is an authorization hole.  Only the second is
        a defect, so this reports which happened rather than asserting on state.

        :return: one of "disturbed" (replicator noticed), "stale-connection"
            (still connected, no data flowing), or "still-syncing" (data delivered on a
            revoked credential)
        """
        for _ in range(timeout):
            status = await replicator.get_status()

            local_docs = await db.get_all_documents(collection)
            if doc_id in {d.id for d in local_docs[collection]}:
                return "still-syncing"

            if status.activity == ReplicatorActivityLevel.STOPPED:
                assert status.error is not None, (
                    "Replicator stopped cleanly after its credential was revoked; expected an error explaining why"
                )
                return "disturbed"
            if status.activity == ReplicatorActivityLevel.OFFLINE:
                return "disturbed"

            await asyncio.sleep(1)

        return "stale-connection"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_revoked_during_continuous_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")
        db = dbs[0]

        self.mark_test_step("Create a session and start a continuous replicator")
        session = await sync_gateway.create_session("travel", "user1")
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorSessionAuthenticator(session.session_id),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait for the replicator to reach IDLE")
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, f"Replicator failed before revocation: {_fmt_error(status.error)}"

        self.mark_test_step("Revoke the session while the replicator is running")
        await sync_gateway.delete_session("travel", session.session_id)
        await sync_gateway.delete_user("travel", "user1")

        self.mark_test_step("Check the session is revoked for new requests")
        # Establishes that the revocation actually took effect, so the continued
        # replication below cannot be explained by a no-op DELETE.
        revoked_client = SyncGatewayUserClient.from_session(sync_gateway.hostname, session, secure=sync_gateway.secure)
        try:
            await _assert_session_rejected(revoked_client, "travel")
        finally:
            await revoked_client.close()

        self.mark_test_step("Write a document 15s after revocation")
        await asyncio.sleep(15)
        await sync_gateway.create_document(
            "travel",
            "post-revocation-doc",
            {"channels": ["*"], "note": "written after the session was revoked"},
            scope="travel",
            collection="airlines",
        )

        self.mark_test_step("Check the established replication is unaffected")
        arrived = False
        for _ in range(30):
            local_docs = await db.get_all_documents("travel.airlines")
            if "post-revocation-doc" in {d.id for d in local_docs["travel.airlines"]}:
                arrived = True
                break
            await asyncio.sleep(1)

        current = await replicator.get_status()
        assert arrived, (
            "A document written after the session was revoked did not reach the client. "
            "Sync Gateway tracks the user object rather than the session for an "
            f"established connection, so replication should have continued "
            f"(replicator is {current.activity}: {_fmt_error(current.error)})"
        )
        assert current.activity == ReplicatorActivityLevel.IDLE, (
            f"Replicator left IDLE after its session was revoked ({current.activity}); "
            "revoking a session should not disturb an established replication"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_jwt_user_revoked_during_continuous_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        """
        OREP-07: the bearer-token equivalent of SREP-11.

        Deletes the user the JWT maps to rather than the token itself -- a signed JWT
        cannot be revoked, so deprovisioning the account is the only way to withdraw
        access before the token expires.  That makes this the realistic revocation
        path for OIDC, and the one an operator would actually use.
        """
        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Configure a `local_jwt` provider and its mapped user")
        private_key = await self._configure_local_jwt(sync_gateway, "travel")

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")

        self.mark_test_step("Start a continuous replicator authenticated by JWT")
        token = generate_jwt(
            private_key,
            subject=_JWT_SUBJECT,
            expires_in=3600,
            kid=_JWT_KID,
            issuer=_JWT_ISSUER,
            audience=_JWT_AUDIENCE,
        )
        replicator = Replicator(
            dbs[0],
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorBearerAuthenticator(token),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, f"JWT replication failed before revocation: {_fmt_error(status.error)}"

        self.mark_test_step("Delete the user the JWT maps to")
        await sync_gateway.delete_user("travel", _JWT_USERNAME)

        self.mark_test_step("Write a document on Sync Gateway to force traffic")
        await sync_gateway.create_document(
            "travel",
            "post-jwt-revocation-doc",
            {"channels": ["*"], "note": "written after the JWT user was deleted"},
            scope="travel",
            collection="airlines",
        )

        self.mark_test_step("Check the deleted identity cannot still receive documents")
        outcome = await self._classify_post_revocation_behaviour(
            replicator, dbs[0], "travel.airlines", "post-jwt-revocation-doc"
        )
        self.mark_test_step(f"Post-revocation behaviour: {outcome}")

        assert outcome != "still-syncing", (
            "A document written after the JWT's user was deleted was still delivered. "
            "Deleting a user does not cut off an established replication, so a "
            "deprovisioned account retains access until its connection drops."
        )
        if outcome == "stale-connection":
            cbl_warning(
                "Replicator remained connected after its JWT user was deleted, but no documents were delivered."
            )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_expired_jwt_then_fresh_token(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        OREP-05: an expired JWT is rejected, and a freshly minted one recovers.

        JWTs make the expiry case cheap to test in a way sessions do not -- `exp` is a
        claim we control, so a token can be born already expired instead of waiting out
        a server-side TTL.
        """
        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Configure a `local_jwt` provider and its mapped user")
        private_key = await self._configure_local_jwt(sync_gateway, "travel")

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")
        db = dbs[0]

        self.mark_test_step("Start a continuous replicator with an already-expired token")
        expired = generate_jwt(
            private_key,
            subject=_JWT_SUBJECT,
            expires_in=-3600,
            kid=_JWT_KID,
            issuer=_JWT_ISSUER,
            audience=_JWT_AUDIENCE,
        )
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorBearerAuthenticator(expired),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Check the expired token is rejected")
        await _assert_auth_rejected(cblpytest, replicator)

        self.mark_test_step("Restart the replicator with a freshly minted token")
        fresh = generate_jwt(
            private_key,
            subject=_JWT_SUBJECT,
            expires_in=3600,
            kid=_JWT_KID,
            issuer=_JWT_ISSUER,
            audience=_JWT_AUDIENCE,
        )
        recovered = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorBearerAuthenticator(fresh),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await recovered.start()

        self.mark_test_step("Check replication now succeeds")
        status = await recovered.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, f"Fresh token was also rejected: {_fmt_error(status.error)}"

        await cblpytest.test_servers[0].cleanup()

    async def _sgw_restart_cycle(
        self,
        cblpytest: CBLPyTest,
        dataset_path: Path,
        authenticator_factory: Callable[[SyncGateway], Awaitable[ReplicatorAuthenticator]],
        label: str,
    ) -> None:
        """
        Shared body for the SGW-restart tests.

        Stops Sync Gateway under a running continuous replicator, writes nothing while
        it is down, restarts it, and checks the replicator reconnects on the *same*
        credential.  The interesting property is that a transport outage must not be
        treated as an auth failure -- an app that re-prompted for credentials every time
        the server bounced would be unusable.
        """
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]

        self.skip_if_not(
            sync_gateway.has_shell2http_sidecar,
            "SGW stop/start requires the shell2http sidecar (AWS topology only)",
        )

        self.mark_test_step("Reset SG and load `travel` dataset")
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step(f"Set up credentials ({label})")
        authenticator = await authenticator_factory(sync_gateway)

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")
        db = dbs[0]

        self.mark_test_step("Start a continuous replicator and wait for IDLE")
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=True,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=authenticator,
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, f"Replication failed before restart: {_fmt_error(status.error)}"

        self.mark_test_step("Stop Sync Gateway")
        await sync_gateway.stop()

        self.mark_test_step("Check the replicator registers the outage")
        went_offline = False
        for _ in range(30):
            current = await replicator.get_status()
            if current.activity in (ReplicatorActivityLevel.OFFLINE, ReplicatorActivityLevel.STOPPED):
                went_offline = True
                break
            await asyncio.sleep(1)
        assert went_offline, "Replicator stayed IDLE after Sync Gateway was stopped"

        self.mark_test_step("Restart Sync Gateway")
        await sync_gateway.start()

        self.mark_test_step("Write a document to confirm replication resumed")
        await sync_gateway.create_document(
            "travel",
            f"post-restart-{label}",
            {"channels": ["*"], "note": "written after Sync Gateway restarted"},
            scope="travel",
            collection="airlines",
        )

        self.mark_test_step("Check the replicator reconnects on the same credential")
        arrived = False
        for _ in range(60):
            current = await replicator.get_status()
            if current.activity == ReplicatorActivityLevel.STOPPED and current.error is not None:
                raise AssertionError(
                    f"Replicator gave up after the restart instead of reconnecting: "
                    f"{_fmt_error(current.error)}. A transport outage should not be "
                    "treated as an auth failure."
                )
            local_docs = await db.get_all_documents("travel.airlines")
            if f"post-restart-{label}" in {d.id for d in local_docs["travel.airlines"]}:
                arrived = True
                break
            await asyncio.sleep(1)

        assert arrived, (
            "Replicator did not resync after Sync Gateway restarted; the document "
            "written post-restart never arrived locally"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sgw_restart_during_session_replication(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """SREP-15: a session survives a Sync Gateway restart and replication resumes."""

        async def make_session_auth(sync_gateway: SyncGateway) -> ReplicatorSessionAuthenticator:
            # Not using session_for() here: the session must outlive the restart, so it
            # is deliberately left for the suite's own teardown rather than scoped.
            session = await sync_gateway.create_session("travel", "user1")
            return ReplicatorSessionAuthenticator(session.session_id)

        await self._sgw_restart_cycle(cblpytest, dataset_path, make_session_auth, "session")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sgw_restart_during_jwt_replication(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        OREP-06 variant: a bearer token survives a Sync Gateway restart.

        Worth testing separately from the session case because the two are stored
        differently -- Sync Gateway sessions are bucket-backed and survive a restart by
        design, whereas a JWT is validated fresh against provider config each time.  If
        the `local_jwt` provider config were lost on restart, this would fail where the
        session test passes.
        """

        async def make_jwt_auth(sync_gateway: SyncGateway) -> ReplicatorBearerAuthenticator:
            private_key = await self._configure_local_jwt(sync_gateway, "travel")
            return ReplicatorBearerAuthenticator(
                generate_jwt(
                    private_key,
                    subject=_JWT_SUBJECT,
                    expires_in=3600,
                    kid=_JWT_KID,
                    issuer=_JWT_ISSUER,
                    audience=_JWT_AUDIENCE,
                )
            )

        await self._sgw_restart_cycle(cblpytest, dataset_path, make_jwt_auth, "jwt")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_guest_replication_allowed(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        """
        SESS-22: with guest access enabled, a replicator with no authenticator syncs.

        The positive counterpart to test_anonymous_replication_rejected -- together they
        show that the guest flag is what decides the outcome, not something incidental
        about the request. Run in isolation, a passing "no credentials works" test proves
        much less: it could pass because authentication is not being enforced at all.

        This is the public-read case CBL JS makes newly relevant. A browser app serving
        openly readable data has no credential to present and no login step, so guest
        access is the only way it can sync -- on the native platforms this path exists
        but is rarely the primary one.
        """
        self.mark_test_step("Reset SG and load `travel` dataset")
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Enable guest access with read access to `travel.airlines`")
        config = await sync_gateway.get_database_config("travel")
        config.guest = {
            "disabled": False,
            "collection_access": {"travel": {"airlines": {"admin_channels": ["*"]}}},
        }
        await sync_gateway.update_database_config("travel", config)

        self.mark_test_step("Check Sync Gateway serves an anonymous request")
        # Confirms guest is live before involving the replicator: if this fails, the
        # config did not take, and a replicator failure below would be misattributed.
        anonymous = SyncGatewayUserClient(sync_gateway.hostname, "", "", secure=sync_gateway.secure)
        try:
            ctx = await anonymous.get_session("travel")
            assert ctx.get("userCtx", {}).get("name") is None, (
                f"Expected an anonymous user context, got {ctx.get('userCtx')}"
            )
        finally:
            await anonymous.close()

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")
        db = dbs[0]

        self.mark_test_step("""
               Start a replicator
               * endpoint: `/travel`
               * collections: `travel.airlines`
               * type: pull
               * continuous: false
               * credentials: none
           """)
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PULL,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=None,
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops and check there is no error")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Guest replication failed: {_fmt_error(status.error)}"

        self.mark_test_step("Check that all documents are replicated correctly")
        # compare_local_and_remote is the real assertion here: a replicator that
        # authenticated as guest but was denied every channel would still reach STOPPED
        # with no error, so "it succeeded" is not enough -- the documents have to match.
        await compare_local_and_remote(
            db,
            sync_gateway,
            ReplicatorType.PULL,
            "travel",
            ["travel.airlines"],
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("continuous", [True, False])
    async def test_network_partition_during_replication(
        self, cblpytest: CBLPyTest, dataset_path: Path, continuous: bool
    ) -> None:
        """
        A continuous replication reconnects after a network outage; a one-shot does not.

        Blocks the client at the Sync Gateway host's firewall rather than stopping the
        service, so this is a true network partition: Sync Gateway keeps running and the
        session stays valid throughout. That isolates the reconnect behaviour from
        anything to do with credentials -- no token is regenerated at any point.

        The one-shot case is parametrized in deliberately: it asserts the *absence* of a
        retry, which is the documented contract. Without it, a future change that made
        one-shot replications reconnect would go unnoticed.
        """
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]

        self.skip_if_not(
            sync_gateway.has_shell2http_sidecar,
            "Firewall simulation requires the shell2http sidecar (AWS topology only)",
        )

        self.mark_test_step("Reset SG and load `travel` dataset")
        await cloud.configure_dataset(dataset_path, "travel")

        self.mark_test_step("Reset local database and load `travel` dataset")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"], dataset="travel")
        db = dbs[0]

        self.mark_test_step(f"Start a {'continuous' if continuous else 'one-shot'} replicator")
        session = await sync_gateway.create_session("travel", "user1")
        replicator = Replicator(
            db,
            sync_gateway.replication_url("travel"),
            replicator_type=ReplicatorType.PUSH_AND_PULL,
            continuous=continuous,
            collections=[ReplicatorCollectionEntry(["travel.airlines"])],
            authenticator=ReplicatorSessionAuthenticator(session.session_id),
            pinned_server_cert=sync_gateway.tls_cert(),
        )
        await replicator.start()
        await replicator.wait_for(ReplicatorActivityLevel.IDLE if continuous else ReplicatorActivityLevel.STOPPED)

        try:
            self.mark_test_step("Block the client at the Sync Gateway host's firewall")
            # await sync_gateway.set_firewall_rules(deny=["0.0.0.0/0"])

            self.mark_test_step("Write a document while the client is partitioned")
            await sync_gateway.create_document(
                "travel",
                "doc-during-partition",
                {"channels": ["*"], "note": "written while the client was cut off"},
                scope="travel",
                collection="airlines",
            )
            await asyncio.sleep(15)

            self.mark_test_step("Restore connectivity")
        finally:
            pass
            # In a finally block so a failed assertion above cannot leave the Sync
            # Gateway host firewalled for the rest of the run.
            # await sync_gateway.reset_firewall()

        self.mark_test_step("Check whether the document arrives without restarting the replicator")
        arrived = False
        for _ in range(60):
            local_docs = await db.get_all_documents("travel.airlines")
            if "doc-during-partition" in {d.id for d in local_docs["travel.airlines"]}:
                arrived = True
                break
            await asyncio.sleep(1)

        status = await replicator.get_status()
        if continuous:
            assert arrived, (
                "A continuous replicator did not resync after the network outage cleared. "
                "Continuous replications are expected to reconnect on their own without "
                f"the session being regenerated (replicator is {status.activity}: "
                f"{_fmt_error(status.error)})"
            )
        else:
            assert not arrived, (
                "A one-shot replicator resynced after the outage. One-shot replications "
                "are not expected to reconnect -- if this now happens, the contract has "
                "changed and callers relying on a single pass may be surprised."
            )

        await cblpytest.test_servers[0].cleanup()
