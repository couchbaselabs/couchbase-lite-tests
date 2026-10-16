import socket
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.syncgateway import DocumentUpdateEntry


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
class TestReplicationMultipleRemotes(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize("replicator_type", [ReplicatorType.PULL, ReplicatorType.PUSH_AND_PULL])
    async def test_replicate_after_doc_synced_through_two_endpoints(
        self, cblpytest: CBLPyTest, dataset_path: Path, replicator_type: ReplicatorType
    ) -> None:
        # Each endpoint URL gets its own remote ID in CBL, so a doc pulled through two URLs and then edited
        # locally makes CBL send three known revs in its reply to `changes`.
        cloud = cblpytest.clusters[0]
        sync_gateway = cloud.sync_gateways[0]
        await self.skip_if_cbl_not(cblpytest.test_servers[0], ">= 4.0.0")
        # The fix for CBG-5978 is in 4.0.9 and 4.1.3, and every release after them. A SpecifierSet can't
        # hold two ranges, so the 4.1 patch releases without the fix are excluded one by one.
        await self.skip_if_sgw_not(sync_gateway, ">= 4.0.9, != 4.1.0, != 4.1.1, != 4.1.2")

        url_by_hostname = sync_gateway.replication_url("names")
        parts = urlsplit(url_by_hostname)
        assert parts.hostname is not None
        ip_address = socket.gethostbyname(parts.hostname)
        self.skip_if_not(ip_address != parts.hostname, "Sync Gateway is configured by IP, so no second URL exists")
        url_by_ip = parts._replace(netloc=parts.netloc.replace(parts.hostname, ip_address, 1)).geturl()

        doc_id = "name_101"
        collection = "_default._default"

        async def replicate(
            endpoint: str, replicator_type: ReplicatorType = ReplicatorType.PULL, continuous: bool = False
        ) -> Replicator:
            replicator = Replicator(
                db,
                endpoint,
                replicator_type=replicator_type,
                continuous=continuous,
                collections=[ReplicatorCollectionEntry([collection])],
                authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                pinned_server_cert=sync_gateway.tls_cert(),
            )
            await replicator.start()
            return replicator

        async def update_on_sync_gateway(last_name: str) -> None:
            existing = await sync_gateway.get_document("names", doc_id)
            assert existing is not None
            body = existing.body
            body["name"]["last"] = last_name
            await sync_gateway.update_documents("names", [DocumentUpdateEntry(doc_id, existing.revid, body)])

        self.mark_test_step("Reset SG and load `names` dataset")
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset empty local database")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]

        self.mark_test_step(f"Pull through {url_by_hostname}")
        status = await (await replicate(url_by_hostname)).wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Error in first pull: {status.error}"

        self.mark_test_step(f"Update `{doc_id}` on SG, then pull it through {url_by_ip}")
        await update_on_sync_gateway("Jones")
        status = await (await replicate(url_by_ip)).wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, f"Error in second pull: {status.error}"

        self.mark_test_step(f"Update `{doc_id}` locally, and update it again on SG")
        async with db.batch_updater() as b:
            b.upsert_document(collection, doc_id, [{"name.last": "Smith"}])
        await update_on_sync_gateway("Brown")

        self.mark_test_step(
            f"Start a continuous {replicator_type} replicator through {url_by_hostname} and wait for it to go idle"
        )
        replicator = await replicate(url_by_hostname, replicator_type, continuous=True)
        status = await replicator.wait_for(ReplicatorActivityLevel.IDLE, timeout=timedelta(seconds=30))
        assert status.error is None, f"Error in continuous replicator: {status.error}"
        assert status.progress.completed, f"Replicator went idle without completing: {status.progress}"
