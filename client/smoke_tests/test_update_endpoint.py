import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.database import Database
from cbltest.api.error import CblTestServerBadResponseError
from cbltest.responses import ServerVariant


class TestUpdateDatabase(CBLTestClass):
    def setup_method(self, method) -> None:
        super().setup_method(method)

        self.db: Database | None = None

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "attempt",
        [
            # Empty
            "",
            # Double open bracket
            "test[[",
            # Missing array index
            "test[]",
            # Invalid array index (word instead of number)
            "test[foo]",
            # Array index where property is expected
            "test.[3]",
            # Double closing bracket
            "test[3]]",
            # Invalid array index (negative)
            "contact.email[-1]",
            # name.first is scalar and has no nested properties
            "name.first.secret",
            # name.first is scalar and has no elements
            "name.first[0]",
            # contact.email is an array and has no nested properties
            "contact.email.secret",
            # name is a dictionary and has no elements
            "name[0]",
        ],
    )
    async def test_bad_updates(self, cblpytest: CBLPyTest, attempt: str) -> None:
        self.mark_test_step(f"Testing bad update with path: {attempt}")

        # JS can accept negative numbers in paths to count from the end
        if "-1" in attempt:
            await self.skip_if_not_platform(
                cblpytest.test_servers[0], ServerVariant.ALL & ~ServerVariant.JS
            )

        if self.db is None:
            self.db = (
                await cblpytest.test_servers[0].create_and_reset_db(
                    ["db1"], dataset="names"
                )
            )[0]

        with pytest.raises(CblTestServerBadResponseError, match="returned 400"):
            async with self.db.batch_updater() as b:
                b.upsert_document("_default._default", "name_1", [{attempt: 5}])

    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "attempt",
        [
            # Add a brand new root key (with the optional JSON path $ for bonus points)
            "$.test",
            # Add a new root key, but this time escape the dollar sign
            "\\$.test",
            # Add a new root key with a nested key inside
            "test2.nested",
            # Begin the list of nested keys from the Ministry of Silly Names
            "test2.\\[",
            "test2.\\]",
            "test2.\\.",
            "test2.foo\\[",
            "test2.foo\\]",
            "test2.foo\\.test2.foo\\[bar",
            "test2.foo\\]bar",
            "test2.foo\\.bar",
            # Add a new root key that contains an array of size 4
            "test3[3]",
            # Add a new root key with a silly, but legal, nested key name
            "test4.$",
            # Add a key to an existing dictionary
            "name.secret",
            # Add a key with a nested key inside to an existing dictionary
            "name.other_secret.super_secret",
            # Replace an element in an array
            "contact.email[0]",
            # Replace dictionary with scalar
            "contact",
            # Replace array with scalar
            "likes",
        ],
    )
    async def test_good_updates(self, cblpytest: CBLPyTest, attempt: str) -> None:
        # The JS test server doesn't support escapes
        if "\\" in attempt:
            await self.skip_if_not_platform(
                cblpytest.test_servers[0], ServerVariant.ALL & ~ServerVariant.JS
            )

        self.mark_test_step(f"Testing good update with path: {attempt}")
        if self.db is None:
            self.db = (
                await cblpytest.test_servers[0].create_and_reset_db(
                    ["db1"], dataset="names"
                )
            )[0]

        async with self.db.batch_updater() as b:
            b.upsert_document("_default._default", "name_1", [{attempt: 5}])

    @pytest.mark.asyncio(loop_scope="session")
    async def test_nonexistent_blob(self, cblpytest: CBLPyTest) -> None:
        db = (
            await cblpytest.test_servers[0].create_and_reset_db(
                ["db1"], dataset="names"
            )
        )[0]

        with pytest.raises(CblTestServerBadResponseError, match="returned 400"):
            async with db.batch_updater() as b:
                b.upsert_document(
                    "_default._default", "name_1", new_blobs={"foo": "bar.png"}
                )
