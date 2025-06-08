import json
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
from cbltest.api.syncgateway import DocumentUpdateEntry
from cbltest.api.test_functions import compare_local_and_remote
from cbltest.responses import ServerVariant


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestReplicatorEncryptionHook(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_replication_complex_doc_encryption(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.C)

        self.mark_test_step("Reset SG and load `posts` dataset")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "posts")

        self.mark_test_step("Reset local database, and load `posts` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="posts"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/posts`
                * collections: `_default.posts`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("posts"),
            collections=[ReplicatorCollectionEntry(["_default.posts"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
            enable_document_listener=True,
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 5, (
            f"Incorrect number of initial documents replicated (expected 5; got {len(lite_all_docs['_default.posts'])}"
        )
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PULL,
            "posts",
            ["_default.posts"],
        )

        self.mark_test_step("""
            Create document in CBL:
                * Create a new document with deeply nested structure:
                  ```json
                  {
                    "level1": {
                      "level2": {
                        "level3": {
                          // ... continue nesting ...
                          "level15": {
                            "encrypted_field": "sensitive_data"
                          }
                        }
                      }
                    }
                  }
                  ```
                * Apply encryption hook to "encrypted_field" at 15th level
        """)
        async with db.batch_updater() as b:
            b.upsert_document(
                "_default.posts",
                "post_1000",
                [
                    {
                        "channels": ["group1"],
                        "nest_1": {
                            "nest_2": {
                                "nest_3": {
                                    "nest_4": {
                                        "nest_5": {
                                            "nest_6": {
                                                "nest_7": {
                                                    "nest_8": {
                                                        "nest_9": {
                                                            "nest_10": {
                                                                "nest_11": {
                                                                    "nest_12": {
                                                                        "nest_13": {
                                                                            "nest_14": EncryptedValue(
                                                                                "secret_password"
                                                                            )
                                                                        }
                                                                    }
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                    }
                ],
            )

        self.mark_test_step("Start the same replicator again")
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )
        lite_all_docs = await db.get_all_documents("_default.posts")
        assert len(lite_all_docs["_default.posts"]) == 6, (
            f"Incorrect number of initial documents replicated (expected 6; got {len(lite_all_docs['_default.posts'])}"
        )

        self.mark_test_step("""
            Check that the document is in SGW:
                * Verify document exists
                * Verify encrypted field is properly encrypted
                * Validate nested structure is preserved
        """)
        doc = await cblpytest.sync_gateways[0].get_document(
            "posts", "post_1000", collection="posts"
        )
        assert doc is not None, "Document should exist in SGW"
        assert doc.body.get("encrypted_field") is not None, (
            "Encrypted value should be present"
        )

        await cblpytest.test_servers[0].cleanup()

    @pytest.mark.asyncio(loop_scope="session")
    async def test_delta_sync_with_encryption(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ):
        await self.skip_if_not_platform(cblpytest.test_servers[0], ServerVariant.C)

        self.mark_test_step(
            "Reset SG and load `travel` dataset with delta sync enabled"
        )
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "travel", ["delta_sync"])

        self.mark_test_step("Reset local database, and load `travel` dataset.")
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="travel"
        )
        db = dbs[0]

        self.mark_test_step("""
            Start a replicator:
                * endpoint: `/travel`
                * collections: `travel.hotels`
                * type: pull
                * continuous: false
                * credentials: user1/pass
        """)
        replicator = Replicator(
            db,
            cblpytest.sync_gateways[0].replication_url("travel"),
            collections=[ReplicatorCollectionEntry(["travel.hotels"])],
            replicator_type=ReplicatorType.PULL,
            authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
            pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
            enable_document_listener=True,
        )
        await replicator.start()

        self.mark_test_step("Wait until the replicator stops.")
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Check that all docs are replicated correctly.")
        lite_all_docs = await db.get_all_documents("travel.hotels")
        assert len(lite_all_docs["travel.hotels"]) == 700, (
            f"Incorrect number of initial documents replicated (expected 700; got {len(lite_all_docs['travel.hotels'])}"
        )
        await compare_local_and_remote(
            db,
            cblpytest.sync_gateways[0],
            ReplicatorType.PULL,
            "travel",
            ["travel.hotels"],
        )

        self.mark_test_step("Record baseline bytes before update")
        _, bytes_written_before = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Get existing document for encryption test")
        original_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_400", "travel", "hotels"
        )
        assert original_doc is not None, "Document hotel_400 should exist"

        self.mark_test_step("Update existing document in SGW with encryption")
        await cblpytest.sync_gateways[0].upsert_documents(
            "travel",
            [
                DocumentUpdateEntry(
                    "hotel_400",
                    original_doc.revid,
                    {
                        "name": "SGW",
                        "encrypted_field": EncryptedValue("secret_password"),
                    },
                )
            ],
            "travel",
            "hotels",
        )

        self.mark_test_step("Start the same replicator again to pull the update")
        await replicator.start()
        status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
        assert status.error is None, (
            f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
        )

        self.mark_test_step("Record the bytes transferred after delta sync.")
        _, bytes_written_after = await cblpytest.sync_gateways[0].bytes_transferred(
            "travel"
        )

        self.mark_test_step("Verify delta sync worked with encryption.")
        sgw_doc = await cblpytest.sync_gateways[0].get_document(
            "travel", "hotel_400", "travel", "hotels"
        )
        assert sgw_doc is not None, "Document should exist in SGW"
        assert sgw_doc.body.get("encrypted_field") is not None, (
            "Encrypted value should be present"
        )

        original_doc_size = len(json.dumps(sgw_doc.body).encode("utf-8"))
        delta_bytes = bytes_written_after - bytes_written_before
        assert delta_bytes < original_doc_size, (
            f"Expected delta to be less than original doc size, but got {delta_bytes} bytes (original doc size: {original_doc_size})"
        )

        await cblpytest.test_servers[0].cleanup()
