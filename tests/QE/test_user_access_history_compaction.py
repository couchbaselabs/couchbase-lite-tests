import asyncio

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.jsonserializable import JSONDictionary
from cbltest.api.replicator_types import ReplicatorBasicAuthenticator, ReplicatorDocumentFlags
from cbltest.api.syncgateway import (
    DatabaseConfig,
    DocumentUpdateEntry,
    IndexConfig,
    ScopeConfig,
    SyncGateway,
    SyncGatewayUserClient,
)
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from shared.backfill_after_offline import backfill_after_offline

PUBLIC_PORT = 4984


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestUserAccessHistoryCompaction(CBLTestClass):
    async def _setup_db(
        self,
        sg: SyncGateway,
        cbs: CouchbaseServer,
        db_name: str,
        bucket_name: str,
        extra_collections: dict[str, list[str]] | None = None,
    ) -> None:
        """Creates a bucket and configures an SGW database on it, optionally with extra named collections."""
        cbs.create_bucket(bucket_name)
        default_collections: dict[str, dict] = {"_default": {}}
        scopes = {"_default": ScopeConfig(collections=default_collections)}
        if extra_collections:
            for scope_name, collection_names in extra_collections.items():
                if scope_name == "_default":
                    cbs.create_collections(bucket_name, "_default", collection_names)
                    for c in collection_names:
                        default_collections[c] = {}
                else:
                    cbs.create_collections(bucket_name, scope_name, collection_names)
                    scopes[scope_name] = ScopeConfig(collections={c: {} for c in collection_names})

        db_payload = DatabaseConfig(bucket=bucket_name, index=IndexConfig(num_replicas=0), scopes=scopes)
        await sg.put_database(db_name, db_payload)
        await SyncGatewayCluster([sg]).wait_for_db_online(db_name)

    def _user_client(self, sg: SyncGateway, username: str, password: str) -> SyncGatewayUserClient:
        """Builds a public-API client for an already-existing user, without resetting their state."""
        return SyncGatewayUserClient(sg.hostname, username, password, port=PUBLIC_PORT, secure=sg.secure)

    def _dump(self, label: str, value: object) -> None:
        """Prints raw diagnostic state for a live run; visible under `pytest -v -s`."""
        print(f"\n[DUMP:{label}] {value!r}")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_new_user_access_history_is_empty(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await self._setup_db(sg, cbs, db_name, "data-bucket")

        self.mark_test_step("Create user 'newuser' with access to channel 'A' (never changed since)")
        await sg.add_user(
            db_name, "newuser", password="pass", collection_access={"_default": {"_default": {"admin_channels": ["A"]}}}
        )

        self.mark_test_step("Get the user's access history")
        history = await sg.get_user_access_history(db_name, "newuser")
        self._dump("get_user_access_history/newuser (never revoked)", history)

        self.mark_test_step("Check that the history is empty")
        assert not history.get("_default", {}).get("_default", [])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_history_for_nonexistent_user_returns_404(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await self._setup_db(sg, cbs, db_name, "data-bucket")

        self.mark_test_step("Get the access history for a user that was never created")
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg.get_user_access_history(db_name, "nonexistent_user")
        self._dump("get_user_access_history/nonexistent-user error", (exc_info.value.code, str(exc_info.value)))

        self.mark_test_step("Check that the request fails with a 404 status")
        assert exc_info.value.code == 404

    @pytest.mark.asyncio(loop_scope="session")
    async def test_grant_then_revoke_channel_appears_in_history(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await self._setup_db(sg, cbs, db_name, "data-bucket")

        self.mark_test_step("Create user 'alice' with access to channel 'A'")
        await sg.add_user(
            db_name, "alice", password="pass", collection_access={"_default": {"_default": {"admin_channels": ["A"]}}}
        )

        self.mark_test_step("Update user 'alice' to remove access to channel 'A' (revoke)")
        await sg.add_user(
            db_name, "alice", password="pass", collection_access={"_default": {"_default": {"admin_channels": []}}}
        )

        self.mark_test_step("Get the user's access history")
        history = await sg.get_user_access_history(db_name, "alice")
        self._dump(
            "get_user_access_history/alice RAW RESPONSE -- settles the {start_seq,end_seq} vs "
            "channel-names-only shape question",
            history,
        )

        self.mark_test_step("Check that channel 'A' appears in the _default._default history")
        assert "A" in history.get("_default", {}).get("_default", [])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_removes_channel_entry_without_touching_live_access(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await self._setup_db(sg, cbs, db_name, "data-bucket")

        self.mark_test_step("Create user 'bob' with access to channels 'A' and 'B'")
        password = "pass"
        await sg.add_user(
            db_name,
            "bob",
            password=password,
            collection_access={"_default": {"_default": {"admin_channels": ["A", "B"]}}},
        )

        self.mark_test_step("Update user 'bob' to remove access to channel 'A' only (revoke 'A', keep 'B')")
        await sg.add_user(
            db_name, "bob", password=password, collection_access={"_default": {"_default": {"admin_channels": ["B"]}}}
        )

        self.mark_test_step("Get the user's access history and check that channel 'A' is present")
        history = await sg.get_user_access_history(db_name, "bob")
        self._dump("get_user_access_history/bob before compact", history)
        assert "A" in history.get("_default", {}).get("_default", [])

        self.mark_test_step("Create a document in channel 'B'")
        await sg.update_documents(db_name, [DocumentUpdateEntry("doc_b", None, {"channels": ["B"]})])

        self.mark_test_step("Compact channel 'A' out of the user's access history")
        compacted = await sg.compact_user_access_history(db_name, "bob", {"_default": {"_default": ["A"]}})
        self._dump("compact_user_access_history/bob", compacted)

        self.mark_test_step("Check that the compact response reports channel 'A' as compacted")
        assert "A" in compacted.get("_default", {}).get("_default", [])

        self.mark_test_step("Get the user's access history again and check that channel 'A' is gone")
        history_after = await sg.get_user_access_history(db_name, "bob")
        self._dump("get_user_access_history/bob after compact", history_after)
        assert "A" not in history_after.get("_default", {}).get("_default", [])

        self.mark_test_step(
            "As user 'bob', fetch all documents and check that the channel-'B' document is still visible"
        )
        user_client = self._user_client(sg, "bob", password)
        try:
            docs = await user_client.get_all_documents(db_name)
            assert any(row.id == "doc_b" for row in docs.rows)
        finally:
            await user_client.close()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_channel_not_in_history_is_idempotent_noop(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await self._setup_db(sg, cbs, db_name, "data-bucket")

        self.mark_test_step("Create user 'carol' with no channel access")
        await sg.add_user(
            db_name, "carol", password="pass", collection_access={"_default": {"_default": {"admin_channels": []}}}
        )

        self.mark_test_step("Compact a channel name that was never granted or revoked for 'carol'")
        first = await sg.compact_user_access_history(db_name, "carol", {"_default": {"_default": ["never-existed"]}})
        self._dump("compact_user_access_history/carol first call", first)

        self.mark_test_step("Check that nothing was reported as compacted")
        assert not first.get("_default", {}).get("_default", [])

        self.mark_test_step("Repeat the same compact call")
        second = await sg.compact_user_access_history(db_name, "carol", {"_default": {"_default": ["never-existed"]}})
        self._dump("compact_user_access_history/carol second call (repeat)", second)

        self.mark_test_step("Check that the result is still empty (idempotent)")
        assert not second.get("_default", {}).get("_default", [])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_multiple_scopes_collections_independently(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step(
            "Create a bucket and configure a Sync Gateway database with a named scope/collection "
            "(scope1.collection1) in addition to _default._default"
        )
        await self._setup_db(sg, cbs, db_name, "data-bucket", extra_collections={"scope1": ["collection1"]})

        self.mark_test_step(
            "Create user 'dave' with access to channel 'A' in _default._default and channel 'X' in scope1.collection1"
        )
        access = {
            "_default": {"_default": {"admin_channels": ["A"]}},
            "scope1": {"collection1": {"admin_channels": ["X"]}},
        }
        await sg.add_user(db_name, "dave", password="pass", collection_access=access)

        self.mark_test_step("Update user 'dave' to revoke both channel 'A' and channel 'X'")
        revoked_access = {
            "_default": {"_default": {"admin_channels": []}},
            "scope1": {"collection1": {"admin_channels": []}},
        }
        await sg.add_user(db_name, "dave", password="pass", collection_access=revoked_access)

        self.mark_test_step("Compact only channel 'A' in _default._default (omit scope1.collection1 from the request)")
        compacted = await sg.compact_user_access_history(db_name, "dave", {"_default": {"_default": ["A"]}})
        self._dump("compact_user_access_history/dave (multi-scope request shape)", compacted)

        self.mark_test_step("Check that the compact response only reports _default._default as trimmed")
        assert "A" in compacted.get("_default", {}).get("_default", [])
        assert not compacted.get("scope1", {}).get("collection1", [])

        self.mark_test_step(
            "Get the user's access history and check that channel 'A' is gone from _default._default while "
            "channel 'X' is still present in scope1.collection1"
        )
        history = await sg.get_user_access_history(db_name, "dave")
        self._dump("get_user_access_history/dave (multi-scope)", history)
        assert "A" not in history.get("_default", {}).get("_default", [])
        assert "X" in history.get("scope1", {}).get("collection1", [])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_default_and_named_collection_history_roundtrip(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step(
            "Create a bucket and configure a Sync Gateway database with a named scope/collection "
            "(scope1.collection1) in addition to _default._default"
        )
        await self._setup_db(sg, cbs, db_name, "data-bucket", extra_collections={"scope1": ["collection1"]})

        self.mark_test_step(
            "Create user 'erin' with access to channel 'A' in _default._default and channel 'X' in scope1.collection1"
        )
        access = {
            "_default": {"_default": {"admin_channels": ["A"]}},
            "scope1": {"collection1": {"admin_channels": ["X"]}},
        }
        await sg.add_user(db_name, "erin", password="pass", collection_access=access)

        self.mark_test_step("Update user 'erin' to revoke both channels")
        revoked_access = {
            "_default": {"_default": {"admin_channels": []}},
            "scope1": {"collection1": {"admin_channels": []}},
        }
        await sg.add_user(db_name, "erin", password="pass", collection_access=revoked_access)

        self.mark_test_step(
            "Get the user's access history and check that both channel 'A' (_default._default) and "
            "channel 'X' (scope1.collection1) are present"
        )
        history = await sg.get_user_access_history(db_name, "erin")
        self._dump("get_user_access_history/erin before compact (default + named collection)", history)
        assert "A" in history.get("_default", {}).get("_default", [])
        assert "X" in history.get("scope1", {}).get("collection1", [])

        self.mark_test_step("Compact both channels in the same request")
        compacted = await sg.compact_user_access_history(
            db_name,
            "erin",
            {
                "_default": {"_default": ["A"]},
                "scope1": {"collection1": ["X"]},
            },
        )
        self._dump("compact_user_access_history/erin", compacted)

        self.mark_test_step("Get the user's access history again and check that both are now gone")
        history_after = await sg.get_user_access_history(db_name, "erin")
        self._dump("get_user_access_history/erin after compact", history_after)
        assert "A" not in history_after.get("_default", {}).get("_default", [])
        assert "X" not in history_after.get("scope1", {}).get("collection1", [])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_role_inherited_channel_not_reachable_via_user_compact_endpoint(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await self._setup_db(sg, cbs, db_name, "data-bucket")

        self.mark_test_step("Create role 'myrole' with access to channel 'ROLE_CHAN'")
        await sg.add_role(db_name, "myrole", {"_default": {"_default": {"admin_channels": ["ROLE_CHAN"]}}})

        self.mark_test_step("Create user 'frank' assigned to role 'myrole', with no direct channel access of their own")
        await sg.add_user(
            db_name,
            "frank",
            password="pass",
            admin_roles=["myrole"],
            collection_access={"_default": {"_default": {"admin_channels": []}}},
        )

        self.mark_test_step("Update role 'myrole' to remove access to channel 'ROLE_CHAN'")
        await sg.add_role(db_name, "myrole", {"_default": {"_default": {"admin_channels": []}}})

        self.mark_test_step(
            "Get user 'frank's access history and check that channel 'ROLE_CHAN' is absent "
            "(the history lives on the role's own principal record, not the user's)"
        )
        history = await sg.get_user_access_history(db_name, "frank")
        self._dump("get_user_access_history/frank (role-inherited channel gap)", history)
        assert "ROLE_CHAN" not in history.get("_default", {}).get("_default", [])

        self.mark_test_step(
            "Compact channel 'ROLE_CHAN' via the user endpoint for 'frank' and check that nothing is reported "
            "as compacted"
        )
        compacted = await sg.compact_user_access_history(db_name, "frank", {"_default": {"_default": ["ROLE_CHAN"]}})
        self._dump("compact_user_access_history/frank (role-inherited channel gap)", compacted)
        assert not compacted.get("_default", {}).get("_default", [])

        self.mark_test_step(
            "Attempt to call a role-scoped access-history-compact endpoint directly and check that it does not "
            "exist (404)"
        )
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg._send_request(
                "post",
                f"/{db_name}/_role/myrole/_access_history/compact",
                JSONDictionary({"channels": {"_default": {"_default": ["ROLE_CHAN"]}}}),
            )
        self._dump(
            "POST /_role/myrole/_access_history/compact error (expect 404 -- endpoint shouldn't exist)",
            (
                exc_info.value.code,
                str(exc_info.value),
            ),
        )
        assert exc_info.value.code == 404

    @pytest.mark.asyncio(loop_scope="session")
    async def test_same_channel_name_two_collections_isolated(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step(
            "Create a bucket and configure a Sync Gateway database with a named scope/collection "
            "(scope1.collection1) in addition to _default._default"
        )
        await self._setup_db(sg, cbs, db_name, "data-bucket", extra_collections={"scope1": ["collection1"]})

        self.mark_test_step(
            "Create user 'grace' with access to channel 'SHARED' in both _default._default and scope1.collection1"
        )
        access = {
            "_default": {"_default": {"admin_channels": ["SHARED"]}},
            "scope1": {"collection1": {"admin_channels": ["SHARED"]}},
        }
        await sg.add_user(db_name, "grace", password="pass", collection_access=access)

        self.mark_test_step("Update user 'grace' to revoke channel 'SHARED' from both collections")
        revoked_access = {
            "_default": {"_default": {"admin_channels": []}},
            "scope1": {"collection1": {"admin_channels": []}},
        }
        await sg.add_user(db_name, "grace", password="pass", collection_access=revoked_access)

        self.mark_test_step("Compact channel 'SHARED' only in _default._default")
        compacted = await sg.compact_user_access_history(db_name, "grace", {"_default": {"_default": ["SHARED"]}})
        self._dump("compact_user_access_history/grace (same channel name, two collections)", compacted)

        self.mark_test_step(
            "Get the user's access history and check that channel 'SHARED' is gone from _default._default "
            "but still present in scope1.collection1"
        )
        history = await sg.get_user_access_history(db_name, "grace")
        self._dump("get_user_access_history/grace (same channel name, two collections)", history)
        assert "SHARED" not in history.get("_default", {}).get("_default", [])
        assert "SHARED" in history.get("scope1", {}).get("collection1", [])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_same_channel_name_two_default_scope_collections_isolated(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step(
            "Create a bucket and configure a Sync Gateway database with an extra named collection "
            "(_default.other) in addition to _default._default"
        )
        await self._setup_db(sg, cbs, db_name, "data-bucket", extra_collections={"_default": ["other"]})

        self.mark_test_step(
            "Create user 'heidi' with access to channel 'SHARED' in both _default._default and _default.other"
        )
        access = {
            "_default": {
                "_default": {"admin_channels": ["SHARED"]},
                "other": {"admin_channels": ["SHARED"]},
            },
        }
        await sg.add_user(db_name, "heidi", password="pass", collection_access=access)

        self.mark_test_step("Update user 'heidi' to revoke channel 'SHARED' from both collections")
        revoked_access = {
            "_default": {
                "_default": {"admin_channels": []},
                "other": {"admin_channels": []},
            },
        }
        await sg.add_user(db_name, "heidi", password="pass", collection_access=revoked_access)

        self.mark_test_step("Compact channel 'SHARED' only in _default._default")
        compacted = await sg.compact_user_access_history(db_name, "heidi", {"_default": {"_default": ["SHARED"]}})
        self._dump("compact_user_access_history/heidi (same channel name, two _default-scope collections)", compacted)

        self.mark_test_step(
            "Get the user's access history and check that channel 'SHARED' is gone from _default._default "
            "but still present in _default.other"
        )
        history = await sg.get_user_access_history(db_name, "heidi")
        self._dump("get_user_access_history/heidi (same channel name, two _default-scope collections)", history)
        assert "SHARED" not in history.get("_default", {}).get("_default", [])
        assert "SHARED" in history.get("_default", {}).get("other", [])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_concurrent_double_compact_clean_conflict(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await self._setup_db(sg, cbs, db_name, "data-bucket")

        self.mark_test_step("Create user 'henry' with access to channel 'A'")
        await sg.add_user(
            db_name, "henry", password="pass", collection_access={"_default": {"_default": {"admin_channels": ["A"]}}}
        )

        self.mark_test_step("Update user 'henry' to revoke channel 'A'")
        await sg.add_user(
            db_name, "henry", password="pass", collection_access={"_default": {"_default": {"admin_channels": []}}}
        )

        self.mark_test_step("Issue two concurrent compact requests for channel 'A' on user 'henry'")
        results = await asyncio.gather(
            sg.compact_user_access_history(db_name, "henry", {"_default": {"_default": ["A"]}}),
            sg.compact_user_access_history(db_name, "henry", {"_default": {"_default": ["A"]}}),
            return_exceptions=True,
        )
        self._dump(
            "concurrent compact_user_access_history/henry raw results (incl. any exceptions)",
            [f"{type(r).__name__}: {r}" for r in results],
        )

        self.mark_test_step(
            "Check that at least one request succeeds, and that any request that fails does so with a "
            "well-formed Sync Gateway error response (not a crash or malformed body)"
        )
        successes = [r for r in results if not isinstance(r, BaseException)]
        failures = [r for r in results if isinstance(r, BaseException)]
        assert len(successes) >= 1
        for failure in failures:
            assert isinstance(failure, CblSyncGatewayBadResponseError)
            self._dump(
                "concurrent compact_user_access_history/henry failure detail",
                (failure.code, str(failure)),
            )

        self.mark_test_step(
            "Get the user's access history afterward and check that channel 'A' is gone and the response is "
            "still well-formed"
        )
        history = await sg.get_user_access_history(db_name, "henry")
        self._dump("get_user_access_history/henry after concurrent compacts", history)
        assert "A" not in history.get("_default", {}).get("_default", [])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_during_live_replication_no_disconnect_no_recompute(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await self._setup_db(sg, cbs, db_name, "data-bucket")

        self.mark_test_step(
            "Create user 'iris' with access to channel 'B', and revoke channel 'A' to give her some access history"
        )
        password = "pass"
        await sg.add_user(
            db_name,
            "iris",
            password=password,
            collection_access={"_default": {"_default": {"admin_channels": ["A", "B"]}}},
        )
        await sg.add_user(
            db_name, "iris", password=password, collection_access={"_default": {"_default": {"admin_channels": ["B"]}}}
        )

        self.mark_test_step("Open a live session as user 'iris' and confirm the changes feed is reachable")
        user_client = self._user_client(sg, "iris", password)
        try:
            changes_before = await user_client.get_changes(db_name)
            self._dump("iris changes feed BEFORE compact (session alive)", "reached OK, no exception raised")

            self.mark_test_step(
                "While that session is still open, compact channel 'A' out of user 'iris's access history"
            )
            compacted = await sg.compact_user_access_history(db_name, "iris", {"_default": {"_default": ["A"]}})
            self._dump("compact_user_access_history/iris while session is live", compacted)

            self.mark_test_step(
                "Using the same still-open session, confirm the changes feed is still reachable immediately "
                "afterward (no forced disconnect)"
            )
            changes_after = await user_client.get_changes(db_name)
            self._dump(
                "iris changes feed AFTER compact (session alive)",
                f"reached OK, no exception raised (last_seq before={changes_before.last_seq!r}, "
                f"after={changes_after.last_seq!r})",
            )

            self.mark_test_step(
                "Create a document in channel 'B' and confirm user 'iris' can still see it through the same "
                "session (current access to 'B' was never touched)"
            )
            await sg.update_documents(db_name, [DocumentUpdateEntry("doc_b", None, {"channels": ["B"]})])
            docs = await user_client.get_all_documents(db_name)
            self._dump("iris get_all_documents after compact", [row.id for row in docs.rows])
            assert any(row.id == "doc_b" for row in docs.rows)
        finally:
            await user_client.close()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_partial_multi_channel_compact_only_found_removed(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await self._setup_db(sg, cbs, db_name, "data-bucket")

        self.mark_test_step("Create user 'jack' with access to channel 'A'")
        await sg.add_user(
            db_name, "jack", password="pass", collection_access={"_default": {"_default": {"admin_channels": ["A"]}}}
        )

        self.mark_test_step(
            "Update user 'jack' to revoke channel 'A' (channel 'NEVER_GRANTED' was never granted at all)"
        )
        await sg.add_user(
            db_name, "jack", password="pass", collection_access={"_default": {"_default": {"admin_channels": []}}}
        )

        self.mark_test_step("Compact both channel 'A' and channel 'NEVER_GRANTED' in the same request")
        compacted = await sg.compact_user_access_history(
            db_name, "jack", {"_default": {"_default": ["A", "NEVER_GRANTED"]}}
        )
        self._dump("compact_user_access_history/jack (partial-success, mixed found/not-found channels)", compacted)

        self.mark_test_step(
            "Check that the response reports channel 'A' as compacted and does not report 'NEVER_GRANTED'"
        )
        compacted_channels = compacted.get("_default", {}).get("_default", [])
        assert "A" in compacted_channels
        assert "NEVER_GRANTED" not in compacted_channels

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_with_duplicate_channel_names_matches_deduplicated_request(
        self, cblpytest: CBLPyTest
    ) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await self._setup_db(sg, cbs, db_name, "data-bucket")

        self.mark_test_step(
            "Create users 'mona' and 'nora', each with access to channels 'ch1' and 'ch2', then revoke both for each"
        )
        access = {"_default": {"_default": {"admin_channels": ["ch1", "ch2"]}}}
        revoked_access = {"_default": {"_default": {"admin_channels": []}}}
        await sg.add_user(db_name, "mona", password="pass", collection_access=access)
        await sg.add_user(db_name, "mona", password="pass", collection_access=revoked_access)
        await sg.add_user(db_name, "nora", password="pass", collection_access=access)
        await sg.add_user(db_name, "nora", password="pass", collection_access=revoked_access)

        self.mark_test_step(
            "Compact 'mona' with a channel list containing a repeated name (['ch1', 'ch1', 'ch2']), and "
            "compact 'nora' with the equivalent deduplicated list (['ch1', 'ch2'])"
        )
        compacted_duplicated = await sg.compact_user_access_history(
            db_name, "mona", {"_default": {"_default": ["ch1", "ch1", "ch2"]}}
        )
        compacted_deduplicated = await sg.compact_user_access_history(
            db_name, "nora", {"_default": {"_default": ["ch1", "ch2"]}}
        )
        self._dump("compact_user_access_history/mona (duplicated request list)", compacted_duplicated)
        self._dump("compact_user_access_history/nora (deduplicated request list)", compacted_deduplicated)

        self.mark_test_step(
            "Check that the duplicated request's response has no duplicate entries and matches the "
            "deduplicated request's response"
        )
        duplicated_channels = compacted_duplicated.get("_default", {}).get("_default", [])
        deduplicated_channels = compacted_deduplicated.get("_default", {}).get("_default", [])
        assert len(duplicated_channels) == len(set(duplicated_channels)), (
            f"Compact response contained duplicate entries: {duplicated_channels}"
        )
        assert set(duplicated_channels) == set(deduplicated_channels) == {"ch1", "ch2"}

        self.mark_test_step("Get both users' access history afterward and check the end state is identical for both")
        history_mona = await sg.get_user_access_history(db_name, "mona")
        history_nora = await sg.get_user_access_history(db_name, "nora")
        assert not history_mona.get("_default", {}).get("_default", [])
        assert not history_nora.get("_default", {}).get("_default", [])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_same_username_different_databases_isolated(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]

        self.mark_test_step("Create two buckets and configure two separate Sync Gateway databases, one on each")
        await self._setup_db(sg, cbs, "db1", "data-bucket-1")
        await self._setup_db(sg, cbs, "db2", "data-bucket-2")

        self.mark_test_step("Create a user with the same name on both databases, each with access to channel 'A'")
        access = {"_default": {"_default": {"admin_channels": ["A"]}}}
        await sg.add_user("db1", "shared_name", password="pass", collection_access=access)
        await sg.add_user("db2", "shared_name", password="pass", collection_access=access)

        self.mark_test_step("Revoke channel 'A' for that user on both databases")
        revoked_access = {"_default": {"_default": {"admin_channels": []}}}
        await sg.add_user("db1", "shared_name", password="pass", collection_access=revoked_access)
        await sg.add_user("db2", "shared_name", password="pass", collection_access=revoked_access)

        self.mark_test_step("Compact channel 'A' for that user on the first database only")
        compacted = await sg.compact_user_access_history("db1", "shared_name", {"_default": {"_default": ["A"]}})
        self._dump("compact_user_access_history/shared_name on db1", compacted)

        self.mark_test_step(
            "Get the user's access history on the second database and check that channel 'A' is still present "
            "there (untouched by the first database's compaction)"
        )
        history_db2 = await sg.get_user_access_history("db2", "shared_name")
        self._dump("get_user_access_history/shared_name on db2 (should be untouched)", history_db2)
        assert "A" in history_db2.get("_default", {}).get("_default", [])

    @pytest.mark.skip(
        reason="No test infra exists for creating a scoped SGW/CBS RBAC admin credential (e.g. 'Application "
        "Read Only'); needs new helper support in client/ before this can be written. See spec for details."
    )
    @pytest.mark.asyncio(loop_scope="session")
    async def test_rbac_read_only_can_get_but_not_compact(self, cblpytest: CBLPyTest) -> None:
        pass

    @pytest.mark.min_test_servers(1)
    @pytest.mark.asyncio(loop_scope="session")
    async def test_offline_revoke_compact_before_reconnect_removes_stale_docs(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"
        doc_id = "doc_a"
        username = "leo"
        password = "pass"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await self._setup_db(sg, cbs, db_name, "data-bucket")

        self.mark_test_step("Create user 'leo' with access to channel 'A'")
        await sg.reset_user(db_name, username, password, ["A"])

        self.mark_test_step("Create a document assigned to channel 'A'")
        await sg.create_document(db_name, doc_id, {"channels": ["A"]})

        self.mark_test_step("Reset a local database and pull as that user so the document replicates to the device")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]
        initial_replicator = await backfill_after_offline(
            db,
            sg,
            db_name,
            ReplicatorBasicAuthenticator(username, password),
            while_offline=lambda: asyncio.sleep(0),
        )
        self._dump(
            "initial_replicator.document_updates (before revoke+compact)",
            [(e.document_id, str(e.flags)) for e in initial_replicator.document_updates],
        )
        assert any(entry.document_id == doc_id for entry in initial_replicator.document_updates), (
            f"{doc_id} did not replicate to the device on initial sync"
        )

        async def _revoke_and_compact_while_offline() -> None:
            self.mark_test_step(
                "While offline, revoke user 'leo's access to channel 'A', then compact channel 'A' out of "
                "the user's access history before the client reconnects"
            )
            await sg.add_user(
                db_name,
                username,
                password=password,
                collection_access={"_default": {"_default": {"admin_channels": []}}},
            )
            compacted = await sg.compact_user_access_history(db_name, username, {"_default": {"_default": ["A"]}})
            self._dump("compact_user_access_history/leo (flagship, during offline window)", compacted)
            assert "A" in compacted.get("_default", {}).get("_default", [])

        self.mark_test_step("Bring the client back online: start a new pull replicator for the same user")
        reconnect_replicator = await backfill_after_offline(
            db,
            sg,
            db_name,
            ReplicatorBasicAuthenticator(username, password),
            while_offline=_revoke_and_compact_while_offline,
        )
        self._dump(
            "reconnect_replicator.document_updates (after revoke+compact)",
            [(e.document_id, str(e.flags)) for e in reconnect_replicator.document_updates],
        )

        self.mark_test_step("Check the device received the document with the access-removed flag set")
        removal_entries = [entry for entry in reconnect_replicator.document_updates if entry.document_id == doc_id]
        assert removal_entries, f"Device never heard about {doc_id} again after reconnecting"
        assert any(entry.flags & ReplicatorDocumentFlags.ACCESS_REMOVED for entry in removal_entries), (
            f"Device reconnected after the offline revoke+compact window but {doc_id} was not reported as "
            f"access-removed: {[str(e.flags) for e in removal_entries]}"
        )

        self.mark_test_step("Check that the channel-'A' document is no longer present on the client")
        all_docs = await db.get_all_documents("_default._default")
        self._dump("db.get_all_documents after reconnect", [doc.id for doc in all_docs["_default._default"]])
        assert not any(doc.id == doc_id for doc in all_docs["_default._default"])
