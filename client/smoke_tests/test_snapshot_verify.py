from typing import Any, Dict, List, Optional, Union
from cbltest import CBLPyTest
from cbltest.api.database_types import SnapshotDocumentEntry
from cbltest.api.database import SnapshotUpdater, DatabaseUpdater
from cbltest.api.error import CblTestServerBadResponseError
import pytest

class TestSnapshotVerify:
    def upsert_multiple(self, instances: List[Union[SnapshotUpdater, DatabaseUpdater]], collection: str, document: str, 
                        new_properties: Optional[List[Dict[str, Any]]] = None, 
                        removed_properties: Optional[List[str]] = None) -> None:
        for instance in instances:
            instance.upsert_document(collection, document, new_properties, removed_properties)

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
        assert verify_result.description is not None

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
        assert verify_result.description is not None

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
        assert verify_result.description is not None
        assert verify_result.actual is not None
        assert verify_result.expected is not None

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
        assert verify_result.description is not None
        assert verify_result.actual is not None
        assert verify_result.expected is not None

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
        assert verify_result.description is not None
        assert verify_result.actual is not None
        assert verify_result.expected is not None
        
    @pytest.mark.asyncio
    async def test_verify_bad_snapshot(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]
        snapshot_id = await db.create_snapshot([
            SnapshotDocumentEntry("_default._default", "name_1")
        ])

        snapshot_updater = SnapshotUpdater(snapshot_id)
        snapshot_updater.purge_document("_default._default", "name_2")
        with pytest.raises(CblTestServerBadResponseError, match="returned 400"):
            verify_result = await db.verify_documents(snapshot_updater)