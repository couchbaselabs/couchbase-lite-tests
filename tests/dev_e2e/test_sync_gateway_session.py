import asyncio
from uuid import uuid4

import pytest
import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.syncgateway import (
    DatabaseConfig,
    DocumentUpdateEntry,
    ScopeConfig,
    SyncGateway,
    SyncGatewayUserClient,
    get_basic_auth_headers,
    get_sync_gateway_session_headers,
)
from cbltest.plugins import cluster_cleanup

DB_NAME = "session_db"
PASSWORD = "pass"
SYNC_FUNCTION = "function(doc, oldDoc) { channel(doc.channels); }"
SHORT_TTL = 3

# Sync Gateway stores a session as the document `_sync:session:<id>`, which Couchbase Server
# refuses once the key is longer than it allows.
OVERSIZED_SESSION_ID = "a" * 237

# Where a session comes from: the admin API, or a login through the public API.
SESSION_SOURCES = ["admin", "public"]


async def create_session(sg: SyncGateway, username: str, source: str) -> str:
    """Creates a session for `username` through the admin API, or by logging in as them through the public API."""
    if source == "admin":
        return await sg.create_session(DB_NAME, username)

    async with sg.get_user_client(get_basic_auth_headers(username, PASSWORD)) as client:
        return await client.create_session(DB_NAME)


async def assert_status(client: SyncGatewayUserClient, doc_id: str, status: int) -> None:
    """Asserts that reading `doc_id` fails with `status`."""
    with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
        await client.get_document(DB_NAME, doc_id)
    assert exc_info.value.code == status, f"Expected {status} reading {doc_id}, got {exc_info.value.code}"


async def assert_unauthorized(client: SyncGatewayUserClient, doc_id: str) -> None:
    """Asserts that reading `doc_id` fails with 401."""
    await assert_status(client, doc_id, 401)


@pytest.mark.min_sync_gateways(1)
class TestSyncGatewaySession(CBLTestClass):
    @pytest_asyncio.fixture(scope="class", autouse=True)
    @classmethod
    async def cluster_cleanup(cls, cblpytest: CBLPyTest) -> None:
        """
        Overrides the function-scoped `cluster_cleanup` fixture: every test works with users of
        its own against one shared database, so cleanup and setup happen once for the class.
        """
        await cluster_cleanup.perform_cleanup(cblpytest)
        await cblpytest.clusters[0].create_database(
            DB_NAME,
            DatabaseConfig(
                bucket=DB_NAME,
                scopes={"_default": ScopeConfig(collections={"_default": {"sync": SYNC_FUNCTION}})},
            ),
        )
        await cblpytest.sync_gateways[0].update_documents(
            DB_NAME,
            [
                DocumentUpdateEntry("doc_a", None, {"channels": ["A"]}),
                DocumentUpdateEntry("doc_b", None, {"channels": ["B"]}),
            ],
        )

    async def _create_user(self, sg: SyncGateway, channels: list[str] | None = None) -> str:
        """Creates a user of this test's own with access to `channels` (default channel A), and returns its name."""
        channels = channels or ["A"]
        username = f"user_{uuid4().hex[:8]}"
        self.mark_test_step(f"Create user {username} with access to channels {channels}")
        await sg.reset_user(DB_NAME, username, PASSWORD, channels)
        return username

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("source", SESSION_SOURCES)
    async def test_session_authenticates_as_user(self, cblpytest: CBLPyTest, source: str) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Create a session for {username} through the {source} API")
        session_id = await create_session(sg, username, source)

        doc_id = f"{username}_doc"
        async with sg.get_user_client(get_sync_gateway_session_headers(session_id)) as client:
            self.mark_test_step("Read doc_a, which is in the user's channel")
            doc = await client.get_document(DB_NAME, "doc_a")
            assert doc.body == {"channels": ["A"]}

            self.mark_test_step("Read doc_b, which is outside the user's channels, and get 403")
            await assert_status(client, "doc_b", 403)

            self.mark_test_step("List all docs and see doc_a but not doc_b")
            all_doc_ids = {row.id for row in (await client.get_all_documents(DB_NAME)).rows}
            assert "doc_a" in all_doc_ids
            assert "doc_b" not in all_doc_ids

            self.mark_test_step(f"Write {doc_id} through the session")
            await client.update_documents(DB_NAME, [DocumentUpdateEntry(doc_id, None, {"channels": ["A"]})])

        self.mark_test_step(f"Read {doc_id} back through the admin API")
        doc = await sg.get_document(DB_NAME, doc_id)
        assert doc.body == {"channels": ["A"]}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_unknown_session_is_rejected(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]

        self.mark_test_step("Read doc_a with a session id that was never created, and get 401")
        async with sg.get_user_client(get_sync_gateway_session_headers("not-a-real-session")) as client:
            await assert_unauthorized(client, "doc_a")

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("source", SESSION_SOURCES)
    @pytest.mark.parametrize("deleted_through", SESSION_SOURCES)
    async def test_deleted_session_is_rejected(self, cblpytest: CBLPyTest, source: str, deleted_through: str) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Create a session for {username} through the {source} API, and read doc_a with it")
        session_id = await create_session(sg, username, source)
        async with sg.get_user_client(get_sync_gateway_session_headers(session_id)) as client:
            await client.get_document(DB_NAME, "doc_a")

            self.mark_test_step(f"Delete the session through the {deleted_through} API")
            if deleted_through == "admin":
                await sg.delete_session(DB_NAME, session_id)
            else:
                await client.delete_session(DB_NAME)

            self.mark_test_step("Read doc_a with the deleted session, and get 401")
            await assert_unauthorized(client, "doc_a")

        # Rosmar deletes a tombstone again without error, where Couchbase Server reports it missing.
        # CBG-4796, fixed by https://github.com/couchbaselabs/rosmar/pull/101
        if await sg.using_rosmar:
            return

        self.mark_test_step("Delete the session again through the admin API, and get 404")
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg.delete_session(DB_NAME, session_id)
        assert exc_info.value.code == 404

    @pytest.mark.asyncio(loop_scope="session")
    async def test_sessions_are_independent(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Create one session for {username} through each API")
        admin_id = await create_session(sg, username, "admin")
        public_id = await create_session(sg, username, "public")
        assert admin_id != public_id

        async with (
            sg.get_user_client(get_sync_gateway_session_headers(admin_id)) as admin_client,
            sg.get_user_client(get_sync_gateway_session_headers(public_id)) as public_client,
        ):
            self.mark_test_step("Read doc_a with both sessions")
            await admin_client.get_document(DB_NAME, "doc_a")
            await public_client.get_document(DB_NAME, "doc_a")

            self.mark_test_step("Log out of the public session")
            await public_client.delete_session(DB_NAME)

            self.mark_test_step("Read doc_a with the public session and get 401, but the admin one still works")
            await assert_unauthorized(public_client, "doc_a")
            await admin_client.get_document(DB_NAME, "doc_a")

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("source", SESSION_SOURCES)
    async def test_deleting_user_invalidates_session(self, cblpytest: CBLPyTest, source: str) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Create a session for {username} through the {source} API, and read doc_a with it")
        session_id = await create_session(sg, username, source)
        async with sg.get_user_client(get_sync_gateway_session_headers(session_id)) as client:
            await client.get_document(DB_NAME, "doc_a")

            self.mark_test_step(f"Delete user {username}")
            await sg.delete_user(DB_NAME, username)

            self.mark_test_step("Read doc_a with the session, and get 401")
            await assert_unauthorized(client, "doc_a")

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("source", SESSION_SOURCES)
    async def test_recreated_user_does_not_inherit_session(self, cblpytest: CBLPyTest, source: str) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Create a session for {username} through the {source} API")
        session_id = await create_session(sg, username, source)

        self.mark_test_step(f"Delete and recreate user {username}")
        await sg.reset_user(DB_NAME, username, PASSWORD, ["A"])

        self.mark_test_step("Read doc_a with the old session, and get 401")
        async with sg.get_user_client(get_sync_gateway_session_headers(session_id)) as client:
            await assert_unauthorized(client, "doc_a")

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("source", SESSION_SOURCES)
    async def test_session_follows_channel_access_changes(self, cblpytest: CBLPyTest, source: str) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Create a session for {username} through the {source} API")
        session_id = await create_session(sg, username, source)
        async with sg.get_user_client(get_sync_gateway_session_headers(session_id)) as client:
            self.mark_test_step("Read doc_b, and get 403")
            await assert_status(client, "doc_b", 403)

            self.mark_test_step(f"Grant {username} access to channel B without recreating the user")
            await sg.add_user(
                DB_NAME,
                username,
                collection_access={"_default": {"_default": {"admin_channels": ["A", "B"]}}},
            )

            self.mark_test_step("Read doc_b with the same session")
            doc = await client.get_document(DB_NAME, "doc_b")
            assert doc.body == {"channels": ["B"]}

    @pytest.mark.asyncio(loop_scope="session")
    async def test_create_session_rejects_invalid_users(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step("Create a session through the admin API for a user that does not exist, and get 404")
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg.create_session(DB_NAME, "nobody")
        assert exc_info.value.code == 404

        self.mark_test_step("Create a session through the admin API for the GUEST user, and get 400")
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg.create_session(DB_NAME, "GUEST")
        assert exc_info.value.code == 400

        self.mark_test_step("Log in through the public API as a user that does not exist, and get 401")
        async with sg.get_user_client(get_basic_auth_headers("nobody", PASSWORD)) as client:
            with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
                await client.create_session(DB_NAME)
            assert exc_info.value.code == 401

        self.mark_test_step(f"Log in through the public API as {username} with a wrong password, and get 401")
        async with sg.get_user_client(get_basic_auth_headers(username, "wrong")) as client:
            with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
                await client.create_session(DB_NAME)
            assert exc_info.value.code == 401

    @pytest.mark.asyncio(loop_scope="session")
    async def test_tampered_session_ids_are_rejected(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Create a session for {username}")
        session_id = await sg.create_session(DB_NAME, username)

        tampered = {
            "truncated": session_id[:-1],
            "extended": f"{session_id}0",
            "uppercased": session_id.upper(),
            "empty": "",
            "user document key": f"_sync:user:{username}",
            "path traversal": f"../_user/{username}",
        }
        for description, tampered_id in tampered.items():
            self.mark_test_step(f"Read doc_a with a {description} session id, and get 401")
            async with sg.get_user_client(get_sync_gateway_session_headers(tampered_id)) as client:
                await assert_unauthorized(client, "doc_a")

    @pytest.mark.skip(reason="bug: CBG-5941: currently this will return a 500 if session id is > 237 characters")
    @pytest.mark.asyncio(loop_scope="session")
    async def test_oversized_session_id_is_rejected(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]

        self.mark_test_step("Read doc_a with an oversized session id, and get 401")
        async with sg.get_user_client(get_sync_gateway_session_headers(OVERSIZED_SESSION_ID)) as client:
            await assert_unauthorized(client, "doc_a")

        self.mark_test_step("Delete the oversized session id through the admin API, and get 404")
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg.delete_session(DB_NAME, OVERSIZED_SESSION_ID)
        assert exc_info.value.code == 404

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("source", SESSION_SOURCES)
    async def test_session_is_rejected_on_admin_port(self, cblpytest: CBLPyTest, source: str) -> None:
        sg = cblpytest.sync_gateways[0]
        if not await sg.admin_interface_authentication:
            pytest.skip("Admin port accepts any request without admin authentication")
        username = await self._create_user(sg)

        self.mark_test_step(f"Create a session for {username} through the {source} API")
        session_id = await create_session(sg, username, source)

        self.mark_test_step("Read doc_a on the admin port with only the session, and get 401")
        async with SyncGatewayUserClient(
            sg.hostname, port=sg.port, secure=sg.secure, headers=get_sync_gateway_session_headers(session_id)
        ) as client:
            await assert_unauthorized(client, "doc_a")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_basic_auth_takes_precedence_over_session(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        session_user = await self._create_user(sg, ["A"])
        basic_user = await self._create_user(sg, ["B"])

        self.mark_test_step(f"Log in as {session_user} through the public API")
        session_id = await create_session(sg, session_user, "public")

        headers = get_sync_gateway_session_headers(session_id) | get_basic_auth_headers(basic_user, PASSWORD)
        async with sg.get_user_client(headers) as client:
            self.mark_test_step(f"Send {session_user}'s session with {basic_user}'s basic auth, and read doc_b")
            await client.get_document(DB_NAME, "doc_b")

            self.mark_test_step("Read doc_a with the same headers, and get 403")
            await assert_status(client, "doc_a", 403)

        self.mark_test_step(f"Send {session_user}'s session with a wrong password for {basic_user}, and get 401")
        headers = get_sync_gateway_session_headers(session_id) | get_basic_auth_headers(basic_user, "wrong")
        async with sg.get_user_client(headers) as client:
            await assert_unauthorized(client, "doc_a")

    @pytest.mark.skip(reason="bug: CBG-5940 disabling a user keeps an invalid session")
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("source", SESSION_SOURCES)
    async def test_disabled_user_session_is_rejected(self, cblpytest: CBLPyTest, source: str) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Create a session for {username} through the {source} API, and read doc_a with it")
        session_id = await create_session(sg, username, source)
        async with sg.get_user_client(get_sync_gateway_session_headers(session_id)) as client:
            await client.get_document(DB_NAME, "doc_a")

            self.mark_test_step(f"Disable user {username}")
            await sg.add_user(DB_NAME, username, disabled=True)

            self.mark_test_step(f"Read doc_a with basic auth for {username}, and get 401")
            async with sg.get_user_client(get_basic_auth_headers(username, PASSWORD)) as basic_client:
                await assert_unauthorized(basic_client, "doc_a")

            self.mark_test_step("Read doc_a with the session, and get 401")
            await assert_unauthorized(client, "doc_a")

            self.mark_test_step(f"Write {username}_doc with the session, and get 401")
            with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
                await client.update_documents(
                    DB_NAME, [DocumentUpdateEntry(f"{username}_doc", None, {"channels": ["A"]})]
                )
            assert exc_info.value.code == 401

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("source", SESSION_SOURCES)
    async def test_password_change_invalidates_session(self, cblpytest: CBLPyTest, source: str) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Create a session for {username} through the {source} API, and read doc_a with it")
        session_id = await create_session(sg, username, source)
        async with sg.get_user_client(get_sync_gateway_session_headers(session_id)) as client:
            await client.get_document(DB_NAME, "doc_a")

            self.mark_test_step(f"Change the password of {username}")
            await sg.add_user(DB_NAME, username, password="newpass")

            self.mark_test_step("Read doc_a with the session, and get 401")
            await assert_unauthorized(client, "doc_a")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delete_user_sessions_invalidates_every_session(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Create one session for {username} through each API")
        session_ids = {source: await create_session(sg, username, source) for source in SESSION_SOURCES}

        self.mark_test_step(f"Delete every session of {username}")
        await sg.delete_user_sessions(DB_NAME, username)

        for source, session_id in session_ids.items():
            self.mark_test_step(f"Read doc_a with the {source} session, and get 401")
            async with sg.get_user_client(get_sync_gateway_session_headers(session_id)) as client:
                await assert_unauthorized(client, "doc_a")

        self.mark_test_step("Log in again through the public API, and read doc_a with the new session")
        new_session_id = await create_session(sg, username, "public")
        async with sg.get_user_client(get_sync_gateway_session_headers(new_session_id)) as client:
            await client.get_document(DB_NAME, "doc_a")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_expires_after_ttl(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Create a session for {username} with a ttl of {SHORT_TTL} seconds")
        session_id = await sg.create_session(DB_NAME, username, ttl=SHORT_TTL)

        async with sg.get_user_client(get_sync_gateway_session_headers(session_id)) as client:
            self.mark_test_step("Read doc_a with the session before it expires")
            await client.get_document(DB_NAME, "doc_a")

            # Any use of the session can extend it, so stay off it until the ttl is over.
            self.mark_test_step(f"Wait {SHORT_TTL + 2} seconds without using the session")
            await asyncio.sleep(SHORT_TTL + 2)

            self.mark_test_step("Read doc_a with the session, and get 401")
            await assert_unauthorized(client, "doc_a")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_session_in_use_is_extended(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Create a session for {username} with a ttl of {SHORT_TTL} seconds")
        session_id = await sg.create_session(DB_NAME, username, ttl=SHORT_TTL)

        async with sg.get_user_client(get_sync_gateway_session_headers(session_id)) as client:
            self.mark_test_step(f"Read doc_a with the session every second for {SHORT_TTL * 3} seconds")
            for _ in range(SHORT_TTL * 3):
                await client.get_document(DB_NAME, "doc_a")
                await asyncio.sleep(1)

            self.mark_test_step(f"Wait {SHORT_TTL + 2} seconds without using the session")
            await asyncio.sleep(SHORT_TTL + 2)

            self.mark_test_step("Read doc_a with the session, and get 401")
            await assert_unauthorized(client, "doc_a")

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "ttl",
        [
            pytest.param(0, id="zero"),
            pytest.param(-1, id="negative"),
            # Past the largest duration in int64 nanoseconds: wraps round to a negative duration.
            pytest.param(9_223_372_037, id="overflows_negative"),
            # Far past it: wraps round to a positive duration of a few years. Fails due to CBG-5942
            # pytest.param(99_999_999_999_999, id="overflows_positive"),
        ],
    )
    async def test_create_session_rejects_invalid_ttl(self, cblpytest: CBLPyTest, ttl: int) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Create a session for {username} with a ttl of {ttl}, and get 400")
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg.create_session(DB_NAME, username, ttl=ttl)
        assert exc_info.value.code == 400

    @pytest.mark.asyncio(loop_scope="session")
    async def test_create_session_rejects_disabled_user(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        username = await self._create_user(sg)

        self.mark_test_step(f"Disable user {username}")
        await sg.add_user(DB_NAME, username, disabled=True)

        self.mark_test_step(f"Create a session for {username} through the admin API, and get 400")
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg.create_session(DB_NAME, username)
        assert exc_info.value.code == 400

        self.mark_test_step(f"Log in as {username} through the public API, and get 401")
        async with sg.get_user_client(get_basic_auth_headers(username, PASSWORD)) as client:
            with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
                await client.create_session(DB_NAME)
            assert exc_info.value.code == 401
