from typing import Any, Dict, List, Optional, Union
from cbltest import CBLPyTest
from cbltest.api.database_types import SnapshotDocumentEntry
from cbltest.api.database import SnapshotUpdater, DatabaseUpdater
from cbltest.api.error import CblTestServerBadResponseError
from cbltest.globals import CBLPyTestGlobal
import pytest

class TestSnapshotVerify:
    def setup_method(self, method):
        # If writing a new test do not forget this step or the test server
        # will not be informed about the currently running test
        CBLPyTestGlobal.running_test_name = method.__name__

    def upsert_multiple(self, instances: List[Union[SnapshotUpdater, DatabaseUpdater]], collection: str, document: str, 
                        new_properties: Optional[List[Dict[str, Any]]] = None, 
                        removed_properties: Optional[List[str]] = None,
                        new_blobs: Optional[Dict[str,str]] = None) -> None:
        for instance in instances:
            instance.upsert_document(collection, document, new_properties, removed_properties, new_blobs)

    def delete_multiple(self, instances: List[Union[SnapshotUpdater, DatabaseUpdater]], collection: str, document: str) -> None:
        for instance in instances:
            instance.delete_document(collection, document)

    def purge_multiple(self, instances: List[Union[SnapshotUpdater, DatabaseUpdater]], collection: str, document: str) -> None:
        for instance in instances:
            instance.purge_document(collection, document)

    @pytest.mark.asyncio
    async def test_verify_good_update(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            self.upsert_multiple([b, snapshot_updater], "_default._default", "name_1", [{"test": "value"}])

        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == True, f"The verification failed: {verify_result.description}"
        assert not verify_result.actual.exists, "Response should not contain 'actual'"
        assert not verify_result.expected.exists, "Response should not contain 'expected'"
        assert verify_result.document is None, "Response should not contain 'document'"

    @pytest.mark.asyncio
    async def test_verify_good_delete(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            self.delete_multiple([b, snapshot_updater], "_default._default", "name_1")

        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == True, f"The verification failed: {verify_result.description}"
        assert not verify_result.actual.exists, "Response should not contain 'actual'"
        assert not verify_result.expected.exists, "Response should not contain 'expected'"
        assert verify_result.document is None, "Response should not contain 'document'"

    @pytest.mark.asyncio
    async def test_verify_bad_delete(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_2")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            b.delete_document([b, snapshot_updater], "_default._default", "name_1")

        snapshot_updater.delete_document("_default._default", "name_2")
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == False, f"The verification passed"
        assert verify_result.description is not None, "Response should contain a description"
        assert not verify_result.actual.exists, "Response should not contain 'actual'"
        assert not verify_result.expected.exists, "Response should not contain 'expected'"
        assert verify_result.document is None, "Response should not contain 'document'"

    @pytest.mark.asyncio
    async def test_verify_good_purge(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            self.purge_multiple([b, snapshot_updater], "_default._default", "name_1")

        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == True, f"The verification failed: {verify_result.description}"
        assert not verify_result.actual.exists, "Response should not contain 'actual'"
        assert not verify_result.expected.exists, "Response should not contain 'expected'"
        assert verify_result.document is None, "Response should not contain 'document'"

    @pytest.mark.asyncio
    async def test_verify_bad_purge(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_2")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            b.purge_document([b, snapshot_updater], "_default._default", "name_1")

        snapshot_updater.purge_document("_default._default", "name_2")
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == False, f"The verification passed"
        assert verify_result.description is not None, "Response should contain a description"
        assert not verify_result.actual.exists, "Response should not contain 'actual'"
        assert not verify_result.expected.exists, "Response should not contain 'expected'"
        assert verify_result.document is None, "Response should not contain 'document'"

    @pytest.mark.asyncio
    async def test_verify_bad_single_dict_update(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "name_1", [{"name.first": "Value"}])

        snapshot_updater.upsert_document("_default._default", "name_1", [{"name.first": "bad_value"}])
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == False, f"The verification passed"
        assert verify_result.description is not None, "Response should contain a description"
        assert verify_result.actual.exists and verify_result.actual.value == "Value", "Incorrect 'actual' in response"
        assert verify_result.expected.exists and verify_result.expected.value == "bad_value", "Incorrect 'expected' in response"
        assert verify_result.document is not None, "Missing document property in response"

    @pytest.mark.asyncio
    async def test_verify_bad_single_array_update(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "name_1", [{"contact.email[0]": "foo@bar.com"}])

        snapshot_updater.upsert_document("_default._default", "name_1", [{"contact.email[0]": "foo@baz.com"}])
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == False, f"The verification passed"
        assert verify_result.description is not None, "Response should contain a description"
        assert verify_result.actual.exists and verify_result.actual.value == "foo@bar.com", "Incorrect 'actual' in response"
        assert verify_result.expected.exists and verify_result.expected.value == "foo@baz.com", "Incorrect 'expected' in response"
        assert verify_result.document is not None, "Missing document property in response"

    @pytest.mark.asyncio
    async def test_verify_bad_array_order_update(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "name_1", [{"contact.email[0]": "foo@bar.com"}])

        snapshot_updater.upsert_document("_default._default", "name_1", [{"contact.email[1]": "foo@bar.com"}])
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == False, f"The verification passed"
        assert verify_result.description is not None, "Response should contain a description"
        assert verify_result.actual.exists and verify_result.actual.value == "foo@bar.com", "Incorrect 'actual' in response"
        assert verify_result.expected.exists and verify_result.expected.value == "shawna.matheney@nosql-matters.org", "Incorrect 'expected' in response"
        assert verify_result.document is not None, "Missing document property in response"

    @pytest.mark.asyncio
    async def test_verify_nonexistent_property(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "name_1", removed_properties=["contact.email"])

        snapshot_updater.upsert_document("_default._default", "name_1", [{"contact.email[1]": "foo@bar.com"}])
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == False, f"The verification passed"
        assert verify_result.description is not None, "Response should contain a description"
        assert not verify_result.actual.exists, "'actual' should be missing"
        assert verify_result.expected.exists and verify_result.expected.value == ["shawna.matheney@nosql-matters.org","foo@bar.com"], "Incorrect 'expected' in response"
        assert verify_result.document is not None, "Missing document property in response"

    @pytest.mark.asyncio
    async def test_verify_bad_remove_property(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "name_1", [{"contact.email[1]": "foo@bar.com"}])

        snapshot_updater.upsert_document("_default._default", "name_1", removed_properties=["contact.email"])
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == False, f"The verification passed"
        assert verify_result.description is not None, "Response should contain a description"
        assert verify_result.actual.exists and verify_result.actual.value == ["shawna.matheney@nosql-matters.org","foo@bar.com"], "Incorrect 'expected' in response"
        assert not verify_result.expected.exists, "'expected' should be missing"
        assert verify_result.document is not None, "Missing document property in response"
        
    @pytest.mark.asyncio
    async def test_verify_bad_snapshot(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        snapshot_updater.purge_document("_default._default", "name_2")
        with pytest.raises(CblTestServerBadResponseError, match="returned 400"):
            await db.verify_documents(snapshot_updater)

    @pytest.mark.asyncio
    async def test_verify_wrongly_existing_doc(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "foo_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "foo_1", [{"contact.email[1]": "foo@bar.com"}])

        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == False, f"The verification passed"
        assert verify_result.description is not None, "Response should contain a description"
        assert not verify_result.actual.exists and not verify_result.actual.exists and verify_result.document is None, \
              "The return value should not have expected, actual, or document"

    @pytest.mark.asyncio
    async def test_verify_wrongly_nonexistent_unmodified(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            b.delete_document("_default._default", "name_1")

        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == False, f"The verification passed"
        assert verify_result.description is not None, "Response should contain a description"
        assert not verify_result.actual.exists and not verify_result.actual.exists and verify_result.document is None, \
            "The return value should not have expected, actual or document"

    @pytest.mark.asyncio
    async def test_verify_wrongly_nonexistent_modified(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        snapshot_updater.upsert_document("_default._default", "name_1", [{"foo": "bar"}])
        async with db.batch_updater() as b:
            b.delete_document("_default._default", "name_1")

        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == False, f"The verification passed"
        assert verify_result.description is not None, "Response should contain a description"
        assert not verify_result.actual.exists and not verify_result.actual.exists and verify_result.document is None, \
            "The return value should not have expected, actual or document"
        
    @pytest.mark.asyncio
    async def test_verify_blob_update(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            self.upsert_multiple([b, snapshot_updater], "_default._default", "name_1", new_blobs={
                "picture": "s1.jpg"
            })

        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == True, f"The verification failed: {verify_result.description}"
        assert not verify_result.actual.exists, "Response should not contain 'actual'"
        assert not verify_result.expected.exists, "Response should not contain 'expected'"
        assert verify_result.document is None, "Response should not contain 'document'"

    @pytest.mark.asyncio
    async def test_verify_bad_blob_update(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "name_1", new_blobs={
                "picture": "s1.jpg"
            })

        snapshot_updater.upsert_document("_default._default", "name_1", new_blobs={
                "picture": "s2.jpg"
            })
        
        verify_result = await db.verify_documents(snapshot_updater)
        assert verify_result.result == False, f"The verification passed"
        assert verify_result.document is not None, "Response should contain 'document'"