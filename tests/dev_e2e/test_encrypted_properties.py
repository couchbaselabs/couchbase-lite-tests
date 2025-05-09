from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database_types import EncryptedValue
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.responses import ServerVariant


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestEncryptedProperties(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_encrypted_push(
        self, dataset_path: Path, cblpytest: CBLPyTest
    ) -> None:
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.C)

        self.mark_test_step("Reset SG and load `names` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step("Reset empty local database")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]

        async with db.batch_updater() as b:
            b.upsert_document(
                "_default._default",
                "secret",
                [{"password": EncryptedValue("secret_password")}],
            )

        self.mark_test_step("""
            Start a replicator: 
                * endpoint: `/names`
                * collections : `_default._default`
                * type: push
                * continuous: false
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("names"),
            replicator_type=ReplicatorType.PUSH,
            collections=[
                ReplicatorCollectionEntry(
                    ["_default._default"],
                )
            ],
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator is stopped.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that the document in SG is not in plaintext")
        pushed_doc = await cblpytest.sync_gateways[0].get_document("names", "secret")
        assert pushed_doc is not None, "Document not found in SG"
        assert "password" not in pushed_doc.body, (
            "The document was pushed without encryption"
        )
        assert "encrypted$password" in pushed_doc.body, (
            "The document was pushed without encryption, but the encrypted field is not present"
        )
        assert (
            pushed_doc.body["encrypted$password"]["ciphertext"] != "secret_password"
        ), "The document was pushed with encryption, but the value is still plaintext"
