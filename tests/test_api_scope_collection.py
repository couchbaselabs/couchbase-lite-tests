import pytest
# import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
# from cbltest.api.database import Database
# from cbltest.jsonhelper import json_equivalent
#
# class TestApiScopeCollection(CBLTestClass):
#     @pytest.mark.asyncio(loop_scope="session")
#     async def test_create_more_than_1000_scopes_collections(self) -> None:
#
#         self.mark_test_step("...Create a bucket...")
#         self.cloud.create_bucket("testBucket")
#         self.mark_test_step("Create 1000 scopes and collections")
#         self.db.create_database()
#         self.cloud.create_user()
#         self.cloud.create_bucket()
#         self.cloud.create_scope_collection(1000)
#         self.cloud.create_scope_collection(1, 1001)
#         self.db.close()


class TestLimitScopesCollections(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_limit_scopes_collections(self, cblpytest: CBLPyTest) -> None:
        """
            * Create exactly 1000 scopes and 10 collections/scope.
            * Verify the creation.
            * Create one more scope.
            * Verify the error message.
            * Create one more collection.
            * Verify the error message.
        """
        bucket_name = "test_bucket"
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.create_bucket(bucket_name)

        # Create 1000 scopes and 1000 collections per scope
        self.mark_test_step("Create 1000 scopes with 1000 collections each.")
        for i in range(1000):
            scope_name = f"scope_{i}"
            await cloud.create_scope(bucket_name, scope_name)
            for j in range(1000):
                collection_name = f"collection_{j}"
                await cloud.create_collection(bucket_name, scope_name, collection_name)

        self.mark_test_step("Verify that all scopes and collections are created successfully.")
        for i in range(1000):
            scope_name = f"scope_{i}"
            for j in range(1000):
                collection_name = f"collection_{j}"
                assert cblpytest.couchbase_servers[0].collection_exists(bucket_name, scope_name, collection_name), (
                    f"Collection {collection_name} in scope {scope_name} was not created successfully."
                )

        self.mark_test_step("Attempt to create one more scope and verify the error.")
        extra_scope = "extra_scope"
        with pytest.raises(Exception, match="Scope limit exceeded"):
            await cloud.create_scope(bucket_name, extra_scope)

        self.mark_test_step("Attempt to create one more collection and verify the error.")
        extra_collection = "extra_collection"
        with pytest.raises(Exception, match="Collection limit exceeded"):
            await cloud.create_collection(bucket_name, "scope_0", extra_collection)

        await cblpytest.test_servers[0].cleanup()