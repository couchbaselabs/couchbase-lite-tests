import asyncio

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.jsonserializable import JSONDictionary
from cbltest.api.replicator import Replicator, ReplicatorCollectionEntry, ReplicatorType
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorDocumentFlags,
    WaitForDocumentEventEntry,
)
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


async def _setup_db(
    sg: SyncGateway,
    sg_cluster: SyncGatewayCluster,
    cbs: CouchbaseServer,
    db_name: str,
    bucket_name: str,
    extra_collections: list[str] | None = None,
) -> None:
    """
    Creates a bucket and configures an SGW database on it, optionally with extra named
    collections alongside _default._default.

    Confirmed live: Sync Gateway allows only one scope per database ("only one named
    scope is supported" 400) -- mixing `_default` with a separately-named scope in one
    database config is not possible. Any extra collections therefore have to live in
    the `_default` scope too, which is all this helper supports.
    """
    cbs.create_bucket(bucket_name)
    default_collections: dict[str, dict] = {"_default": {}}
    if extra_collections:
        cbs.create_collections(bucket_name, "_default", extra_collections)
        for c in extra_collections:
            default_collections[c] = {}

    db_payload = DatabaseConfig(
        bucket=bucket_name,
        index=IndexConfig(num_replicas=0),
        scopes={
            "_default": ScopeConfig(
                collections={name: {"sync": "function(doc){channel(doc.channels);}"} for name in default_collections}
            )
        },
    )
    await sg_cluster.create_database(db_name, db_payload)
    await SyncGatewayCluster([sg]).wait_for_db_online(db_name)


def _user_client(sg: SyncGateway, username: str, password: str) -> SyncGatewayUserClient:
    """Builds a public-API client for an already-existing user, without resetting their state."""
    return SyncGatewayUserClient(sg.hostname, username, password, port=PUBLIC_PORT, secure=sg.secure)


def _channels(response: dict, scope: str = "_default", collection: str = "_default") -> list[str]:
    """
    Extracts the channel-name list for scope/collection from a get/compact_user_access_history
    response. Confirmed live: Sync Gateway represents an empty collection entry as JSON `null`
    (not an empty list, and not an absent key), so `.get(scope, {}).get(collection, [])` is not
    safe on its own -- `dict.get`'s default only applies when the key is missing, not when its
    value is `None`.
    """
    return response.get(scope, {}).get(collection) or []


@pytest.mark.sgw
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestUserAccessHistoryCompaction(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_new_user_access_history_is_empty(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await _setup_db(sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket")

        self.mark_test_step("Create user 'newuser' with access to channel 'A' (never changed since)")
        await sg.add_user(
            db_name, "newuser", password="pass", collection_access={"_default": {"_default": {"admin_channels": ["A"]}}}
        )

        self.mark_test_step("Get the user's access history")
        history = await sg.get_user_access_history(db_name, "newuser")

        self.mark_test_step("Check that the history is empty")
        assert not _channels(history)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_history_for_nonexistent_user_returns_404(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await _setup_db(sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket")

        self.mark_test_step("Get the access history for a user that was never created")
        with pytest.raises(CblSyncGatewayBadResponseError) as exc_info:
            await sg.get_user_access_history(db_name, "nonexistent_user")

        self.mark_test_step("Check that the request fails with a 404 status")
        assert exc_info.value.code == 404

    @pytest.mark.asyncio(loop_scope="session")
    async def test_grant_then_revoke_channel_appears_in_history(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await _setup_db(sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket")

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

        self.mark_test_step("Check that channel 'A' appears in the _default._default history")
        assert "A" in _channels(history)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_removes_channel_entry_without_touching_live_access(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await _setup_db(sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket")

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
        assert "A" in _channels(history)

        self.mark_test_step("Create a document in channel 'B'")
        await sg.update_documents(db_name, [DocumentUpdateEntry("doc_b", None, {"channels": ["B"]})])

        self.mark_test_step("Compact channel 'A' out of the user's access history")
        compacted = await sg.compact_user_access_history(db_name, "bob", {"_default": {"_default": ["A"]}})

        self.mark_test_step("Check that the compact response reports channel 'A' as compacted")
        assert "A" in _channels(compacted)

        self.mark_test_step("Get the user's access history again and check that channel 'A' is gone")
        history_after = await sg.get_user_access_history(db_name, "bob")
        assert "A" not in _channels(history_after)

        self.mark_test_step(
            "As user 'bob', fetch all documents and check that the channel-'B' document is still visible"
        )
        user_client = _user_client(sg, "bob", password)
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
        await _setup_db(sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket")

        self.mark_test_step("Create user 'carol' with no channel access")
        await sg.add_user(
            db_name, "carol", password="pass", collection_access={"_default": {"_default": {"admin_channels": []}}}
        )

        self.mark_test_step("Compact a channel name that was never granted or revoked for 'carol'")
        first = await sg.compact_user_access_history(db_name, "carol", {"_default": {"_default": ["never-existed"]}})

        self.mark_test_step("Check that nothing was reported as compacted")
        assert not _channels(first)

        self.mark_test_step("Repeat the same compact call")
        second = await sg.compact_user_access_history(db_name, "carol", {"_default": {"_default": ["never-existed"]}})

        self.mark_test_step("Check that the result is still empty (idempotent)")
        assert not _channels(second)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_multiple_collections_independently(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step(
            "Create a bucket and configure a Sync Gateway database with an extra named collection "
            "(_default.other) in addition to _default._default"
        )
        await _setup_db(
            sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket", extra_collections=["other"]
        )

        self.mark_test_step(
            "Create user 'dave' with access to channel 'A' in _default._default and channel 'X' in _default.other"
        )
        access = {
            "_default": {
                "_default": {"admin_channels": ["A"]},
                "other": {"admin_channels": ["X"]},
            },
        }
        await sg.add_user(db_name, "dave", password="pass", collection_access=access)

        self.mark_test_step("Update user 'dave' to revoke both channel 'A' and channel 'X'")
        revoked_access = {
            "_default": {
                "_default": {"admin_channels": []},
                "other": {"admin_channels": []},
            },
        }
        await sg.add_user(db_name, "dave", password="pass", collection_access=revoked_access)

        self.mark_test_step("Compact only channel 'A' in _default._default (omit _default.other from the request)")
        compacted = await sg.compact_user_access_history(db_name, "dave", {"_default": {"_default": ["A"]}})

        self.mark_test_step("Check that the compact response only reports _default._default as trimmed")
        assert "A" in _channels(compacted)
        assert not _channels(compacted, collection="other")

        self.mark_test_step(
            "Get the user's access history and check that channel 'A' is gone from _default._default while "
            "channel 'X' is still present in _default.other"
        )
        history = await sg.get_user_access_history(db_name, "dave")
        assert "A" not in _channels(history)
        assert "X" in _channels(history, collection="other")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_default_and_named_collection_history_roundtrip(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step(
            "Create a bucket and configure a Sync Gateway database with an extra named collection "
            "(_default.other) in addition to _default._default"
        )
        await _setup_db(
            sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket", extra_collections=["other"]
        )

        self.mark_test_step(
            "Create user 'erin' with access to channel 'A' in _default._default and channel 'X' in _default.other"
        )
        access = {
            "_default": {
                "_default": {"admin_channels": ["A"]},
                "other": {"admin_channels": ["X"]},
            },
        }
        await sg.add_user(db_name, "erin", password="pass", collection_access=access)

        self.mark_test_step("Update user 'erin' to revoke both channels")
        revoked_access = {
            "_default": {
                "_default": {"admin_channels": []},
                "other": {"admin_channels": []},
            },
        }
        await sg.add_user(db_name, "erin", password="pass", collection_access=revoked_access)

        self.mark_test_step(
            "Get the user's access history and check that both channel 'A' (_default._default) and "
            "channel 'X' (_default.other) are present"
        )
        history = await sg.get_user_access_history(db_name, "erin")
        assert "A" in _channels(history)
        assert "X" in _channels(history, collection="other")

        self.mark_test_step("Compact both channels in the same request")
        await sg.compact_user_access_history(
            db_name,
            "erin",
            {"_default": {"_default": ["A"], "other": ["X"]}},
        )

        self.mark_test_step("Get the user's access history again and check that both are now gone")
        history_after = await sg.get_user_access_history(db_name, "erin")
        assert "A" not in _channels(history_after)
        assert "X" not in _channels(history_after, collection="other")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_role_inherited_channel_not_reachable_via_user_compact_endpoint(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await _setup_db(sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket")

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
        assert "ROLE_CHAN" not in _channels(history)

        self.mark_test_step(
            "Compact channel 'ROLE_CHAN' via the user endpoint for 'frank' and check that nothing is reported "
            "as compacted"
        )
        compacted = await sg.compact_user_access_history(db_name, "frank", {"_default": {"_default": ["ROLE_CHAN"]}})
        assert not _channels(compacted)

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
        assert exc_info.value.code == 404

    @pytest.mark.asyncio(loop_scope="session")
    async def test_same_channel_name_two_collections_isolated(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step(
            "Create a bucket and configure a Sync Gateway database with an extra named collection "
            "(_default.other) in addition to _default._default"
        )
        await _setup_db(
            sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket", extra_collections=["other"]
        )

        self.mark_test_step(
            "Create user 'grace' with access to channel 'SHARED' in both _default._default and _default.other"
        )
        access = {
            "_default": {
                "_default": {"admin_channels": ["SHARED"]},
                "other": {"admin_channels": ["SHARED"]},
            },
        }
        await sg.add_user(db_name, "grace", password="pass", collection_access=access)

        self.mark_test_step("Update user 'grace' to revoke channel 'SHARED' from both collections")
        revoked_access = {
            "_default": {
                "_default": {"admin_channels": []},
                "other": {"admin_channels": []},
            },
        }
        await sg.add_user(db_name, "grace", password="pass", collection_access=revoked_access)

        self.mark_test_step("Compact channel 'SHARED' only in _default._default")
        await sg.compact_user_access_history(db_name, "grace", {"_default": {"_default": ["SHARED"]}})

        self.mark_test_step(
            "Get the user's access history and check that channel 'SHARED' is gone from _default._default "
            "but still present in _default.other"
        )
        history = await sg.get_user_access_history(db_name, "grace")
        assert "SHARED" not in _channels(history)
        assert "SHARED" in _channels(history, collection="other")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_concurrent_double_compact_clean_conflict(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await _setup_db(sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket")

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

        self.mark_test_step(
            "Check that at least one request succeeds, and that any request that fails does so with a "
            "well-formed Sync Gateway error response (not a crash or malformed body)"
        )
        successes = [r for r in results if not isinstance(r, BaseException)]
        failures = [r for r in results if isinstance(r, BaseException)]
        assert len(successes) >= 1
        for failure in failures:
            assert isinstance(failure, CblSyncGatewayBadResponseError)

        self.mark_test_step(
            "Get the user's access history afterward and check that channel 'A' is gone and the response is "
            "still well-formed"
        )
        history = await sg.get_user_access_history(db_name, "henry")
        assert "A" not in _channels(history)

    @pytest.mark.min_test_servers(1)
    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_during_live_replication_no_disconnect_no_recompute(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await _setup_db(sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket")

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

        self.mark_test_step(
            "Reset a local database and start a continuous pull replicator for user 'iris', waiting for it to "
            "reach idle"
        )
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"]))[0]
        replicator = Replicator(
            db,
            sg.replication_url(db_name),
            replicator_type=ReplicatorType.PULL,
            continuous=True,
            authenticator=ReplicatorBasicAuthenticator("iris", password),
            collections=[ReplicatorCollectionEntry()],
            enable_document_listener=True,
            pinned_server_cert=sg.tls_cert(),
        )
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE)
        assert status.error is None, (
            f"Replicator failed to reach idle before compact: ({status.error.domain} / {status.error.code}) "
            f"{status.error.message}"
        )

        self.mark_test_step(
            "While that replicator is still continuously connected, compact channel 'A' out of user 'iris's "
            "access history"
        )
        await sg.compact_user_access_history(db_name, "iris", {"_default": {"_default": ["A"]}})

        self.mark_test_step(
            "Check that the replicator is still running normally afterward, with no error and no forced disconnect"
        )
        status_after_compact = await replicator.get_status()
        assert status_after_compact.error is None, (
            f"Replicator reported an error after compact: ({status_after_compact.error.domain} / "
            f"{status_after_compact.error.code}) {status_after_compact.error.message}"
        )
        assert status_after_compact.activity != ReplicatorActivityLevel.STOPPED, (
            "Replicator was disconnected/stopped by the access-history compact"
        )

        self.mark_test_step(
            "Create a document in channel 'B' and confirm the still-connected replicator pulls it down without "
            "needing to reconnect or resync (current access to 'B' was never touched)"
        )
        replicator.clear_document_updates()
        await sg.update_documents(db_name, [DocumentUpdateEntry("doc_b", None, {"channels": ["B"]})])
        status_after_doc = await replicator.wait_for_all_doc_events(
            {WaitForDocumentEventEntry("_default._default", "doc_b", ReplicatorType.PULL, ReplicatorDocumentFlags.NONE)}
        )
        assert status_after_doc.error is None, (
            f"Replicator errored while pulling doc_b: ({status_after_doc.error.domain} / "
            f"{status_after_doc.error.code}) {status_after_doc.error.message}"
        )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_partial_multi_channel_compact_only_found_removed(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await _setup_db(sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket")

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

        self.mark_test_step(
            "Check that the response reports channel 'A' as compacted and does not report 'NEVER_GRANTED'"
        )
        compacted_channels = _channels(compacted)
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
        await _setup_db(sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket")

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

        self.mark_test_step(
            "Check that the duplicated request's response has no duplicate entries and matches the "
            "deduplicated request's response"
        )
        duplicated_channels = _channels(compacted_duplicated)
        deduplicated_channels = _channels(compacted_deduplicated)
        assert len(duplicated_channels) == len(set(duplicated_channels)), (
            f"Compact response contained duplicate entries: {duplicated_channels}"
        )
        assert set(duplicated_channels) == set(deduplicated_channels) == {"ch1", "ch2"}

        self.mark_test_step("Get both users' access history afterward and check the end state is identical for both")
        history_mona = await sg.get_user_access_history(db_name, "mona")
        history_nora = await sg.get_user_access_history(db_name, "nora")
        assert not _channels(history_mona)
        assert not _channels(history_nora)

    @pytest.mark.asyncio(loop_scope="session")
    async def test_same_username_different_databases_isolated(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]

        self.mark_test_step("Create two buckets and configure two separate Sync Gateway databases, one on each")
        await _setup_db(sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, "db1", "data-bucket-1")
        await _setup_db(sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, "db2", "data-bucket-2")

        self.mark_test_step("Create a user with the same name on both databases, each with access to channel 'A'")
        access = {"_default": {"_default": {"admin_channels": ["A"]}}}
        await sg.add_user("db1", "shared_name", password="pass", collection_access=access)
        await sg.add_user("db2", "shared_name", password="pass", collection_access=access)

        self.mark_test_step("Revoke channel 'A' for that user on both databases")
        revoked_access = {"_default": {"_default": {"admin_channels": []}}}
        await sg.add_user("db1", "shared_name", password="pass", collection_access=revoked_access)
        await sg.add_user("db2", "shared_name", password="pass", collection_access=revoked_access)

        self.mark_test_step("Compact channel 'A' for that user on the first database only")
        await sg.compact_user_access_history("db1", "shared_name", {"_default": {"_default": ["A"]}})

        self.mark_test_step(
            "Get the user's access history on the second database and check that channel 'A' is still present "
            "there (untouched by the first database's compaction)"
        )
        history_db2 = await sg.get_user_access_history("db2", "shared_name")
        assert "A" in _channels(history_db2)

    @pytest.mark.skip(
        reason="No test infra exists for creating a scoped SGW/CBS RBAC admin credential (e.g. 'Application "
        "Read Only'); needs new helper support in client/ before this can be written. See spec for details."
    )
    @pytest.mark.asyncio(loop_scope="session")
    async def test_rbac_read_only_can_get_but_not_compact(self, cblpytest: CBLPyTest) -> None:
        pass

    @pytest.mark.min_test_servers(1)
    @pytest.mark.asyncio(loop_scope="session")
    async def test_compact_while_client_offline_leaves_stale_access_undetected(self, cblpytest: CBLPyTest) -> None:
        sg = cblpytest.sync_gateways[0]
        cbs = cblpytest.couchbase_servers[0]
        db_name = "db"
        doc_id = "doc_a"
        username = "leo"
        password = "pass"

        self.mark_test_step("Create a bucket and configure a Sync Gateway database on it")
        await _setup_db(sg, cblpytest.clusters[0].sync_gateway_cluster, cbs, db_name, "data-bucket")

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
            assert "A" in _channels(compacted)

        self.mark_test_step("Bring the client back online: start a new pull replicator for the same user")
        reconnect_replicator = await backfill_after_offline(
            db,
            sg,
            db_name,
            ReplicatorBasicAuthenticator(username, password),
            while_offline=_revoke_and_compact_while_offline,
        )

        self.mark_test_step(
            "Check that the device received no notification about 'doc_a' at all -- compacting the user's "
            "access history for channel 'A' before the client resumed left Sync Gateway with no history to "
            "compute the revocation against, which is the documented risk of compacting history a still-"
            "offline client may still depend on"
        )
        removal_entries = [entry for entry in reconnect_replicator.document_updates if entry.document_id == doc_id]
        assert not removal_entries, (
            f"Expected no update for {doc_id} on reconnect (compacting access history out from under a "
            f"still-offline client is expected to suppress its revocation notice), but got: "
            f"{[str(e.flags) for e in removal_entries]}"
        )

        self.mark_test_step(
            "Check that the now-inaccessible channel-'A' document is still present on the client -- the "
            "documented risk outcome of compacting access history the client's reconnect needed"
        )
        all_docs = await db.get_all_documents("_default._default")
        assert any(doc.id == doc_id for doc in all_docs["_default._default"]), (
            f"Expected the stale {doc_id} to remain on the client since it was never told to remove it"
        )
