from varname import nameof

from cbltest.assertions import _assert_not_null
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.syncgateway import PutDatabasePayload, SyncGateway
from cbltest.api.couchbaseserver import CouchbaseServer

class CouchbaseCloud:
    """
    A class that performs operations that require coordination between both Sync Gateway and Couchbase Server
    """

    def __init__(self, sync_gateway: SyncGateway, server: CouchbaseServer):
        self.__sync_gateway = sync_gateway
        self.__couchbase_server = server

    async def put_empty_database(self, db_name: str, db_payload: PutDatabasePayload, bucket_name: str) -> None:
        """
        Creates a database, ensuring that it is in an empty state when finished

        :param db_name: The name of the DB for Sync Gateway
        :param db_payload: The options for the DB in Sync Gateway
        :param bucket_name: The name of the bucket in Couchbase Server
        """

        _assert_not_null(db_name, nameof(db_name))
        _assert_not_null(bucket_name, nameof(bucket_name))
        try:
            self.__couchbase_server.create_bucket(bucket_name)
            await self.__sync_gateway.put_database(db_name, db_payload)
        except CblSyncGatewayBadResponseError as e:
            if e.code != 412:
                raise

            await self.__sync_gateway.delete_database(db_name)
            self.__couchbase_server.drop_bucket(bucket_name)
            self.__couchbase_server.create_bucket(bucket_name)
            await self.__sync_gateway.put_database(db_name, db_payload)