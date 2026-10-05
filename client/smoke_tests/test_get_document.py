import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database_types import DocumentEntry
from cbltest.api.error import CblTestServerBadResponseError


class TestGetDocument(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_existing_document(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"]))[0]
        async with db.batch_updater() as b:
            b.upsert_document("_default._default", "doc1", [{"name": "test"}])

        doc = await db.get_document(DocumentEntry("_default._default", "doc1"))
        assert doc.id == "doc1"
        assert doc.body["name"] == "test"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_get_missing_document_returns_404(self, cblpytest: CBLPyTest) -> None:
        db = (await cblpytest.test_servers[0].create_and_reset_db(["db1"]))[0]

        with pytest.raises(CblTestServerBadResponseError, match="POST /getDocument returned 404") as exc_info:
            await db.get_document(DocumentEntry("_default._default", "missing"))

        assert exc_info.value.code == 404
