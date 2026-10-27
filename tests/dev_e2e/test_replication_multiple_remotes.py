import socket
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass, CouchbaseLiteFeature
from cbltest.api.database_types import DocumentEntry
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorConflictResolver,
    ReplicatorType,
)
from packaging.specifiers import SpecifierSet
from packaging.version import Version


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
class TestReplicationMultipleRemotes(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("replicator_type", [ReplicatorType.PULL, ReplicatorType.PUSH_AND_PULL])
    async def test_replicate_after_doc_synced_through_two_endpoints(
        self, cblpytest: CBLPyTest, dataset_path: Path, replicator_type: ReplicatorType
    ) -> None:
        await self.skip_if_not_supports(cblpytest.test_servers[0], CouchbaseLiteFeature.CUSTOM_CONFLICT_RESOLVER)
        # Each endpoint URL gets its own remote ID in CBL, so a doc pulled through two URLs and then edited
        # locally makes CBL send three known revs in its reply to `changes`.
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        sgw_version = Version((await sync_gateway.get_version()).version)
        self.skip_if_not(
            sgw_version in SpecifierSet(">=4.0.9,!=4.1.0,!=4.1.1,!=4.1.2"),
            f"SGW {sgw_version} lacks the fix for CBG-5978",
        )

        url_by_hostname = sync_gateway.replication_url("names")
        parts = urlsplit(url_by_hostname)
        assert parts.hostname is not None
        ip_address = socket.gethostbyname(parts.hostname)
        self.skip_if_not(ip_address != parts.hostname, "Sync Gateway is configured by IP, so no second URL exists")
        url_by_ip = parts._replace(netloc=f"{ip_address}:{parts.port}" if parts.port else ip_address).geturl()

        doc_id = "doc1"
        collection = "_default._default"

        async def replicate(endpoint: str, replication_type: ReplicatorType = ReplicatorType.PULL) -> None:
            """Runs a one-shot replication through the endpoint, resolving conflicts in favour of SG."""
            replicator = Replicator(
                db,
                endpoint,
                replicator_type=replication_type,
                collections=[
                    ReplicatorCollectionEntry([collection], conflict_resolver=ReplicatorConflictResolver("remote-wins"))
                ],
                authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                pinned_server_cert=sync_gateway.tls_cert(),
            )
            await replicator.start()
            status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
            assert status.error is None, f"Error replicating through {endpoint}: {status.error}"

        async def assert_local_body(expected: dict) -> None:
            """Checks that the local copy of the test document has the given body."""
            doc = await db.get_document(DocumentEntry(collection, doc_id))
            assert doc.body == expected, f"Local `{doc_id}` is {doc.body}, expected {expected}"

        self.mark_test_step("Reset SG and load `names` dataset")
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset empty local database")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]

        self.mark_test_step(f"Create `{doc_id}` on SG, then pull it through {url_by_hostname}")
        rev = (await sync_gateway.create_document("names", doc_id, {"write": 1}, wait_for_caching_feed=True)).revid
        await replicate(url_by_hostname)
        await assert_local_body({"write": 1})

        self.mark_test_step(f"Update `{doc_id}` on SG, then pull it through {url_by_ip}")
        rev = (await sync_gateway.update_document("names", doc_id, {"write": 2}, rev, wait_for_caching_feed=True)).revid
        await replicate(url_by_ip)
        await assert_local_body({"write": 2})

        self.mark_test_step(f"Update `{doc_id}` locally, and update it again on SG")
        async with db.batch_updater() as b:
            b.upsert_document(collection, doc_id, [{"write": "local"}])
        await sync_gateway.update_document("names", doc_id, {"write": 3}, rev, wait_for_caching_feed=True)

        self.mark_test_step(f"Run a {replicator_type} replication through {url_by_hostname}")
        await replicate(url_by_hostname, replicator_type)
        await assert_local_body({"write": 3})
