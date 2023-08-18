from json import load
from pathlib import Path
from typing import cast
from varname import nameof

from cbltest.assertions import _assert_not_null
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.syncgateway import PutDatabasePayload, SyncGateway
from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.jsonhelper import _get_typed_required

class CouchbaseCloud:
    """
    A class that performs operations that require coordination between both Sync Gateway and Couchbase Server
    """

    def __init__(self, sync_gateway: SyncGateway, server: CouchbaseServer):
        self.__sync_gateway = sync_gateway
        self.__couchbase_server = server

    def _create_collections(self, db_payload: PutDatabasePayload) -> None:
        for scope in db_payload.scopes():
            self.__couchbase_server.create_collections(db_payload.bucket, scope, db_payload.collections(scope))

    async def configure_dataset(self, dataset_path: Path, dataset_name: str) -> None:
        """
        Creates a database, ensuring that it is in an empty state when finished

        :param dataset_path: The path to the folder containing the configuration data
        :param dataset_name: The name of the dataset configuration to use
        
        .. note:: The expected format is a file named <database_name>-sg-config.json
                  containing a config and users key, for use with the PUT /<db> and
                  PUT /<db>/<user> endpoints and a file named <database_name>-sg.json
                  containing the actual data to populate.
        """
        _assert_not_null(dataset_path, nameof(dataset_path))
        _assert_not_null(dataset_name, nameof(dataset_name))

        config_filepath = dataset_path / f"{dataset_name}-sg-config.json"
        data_filepath = dataset_path / f"{dataset_name}-sg.json"
        if not config_filepath.exists():
            raise FileNotFoundError(f"Configuration file {dataset_name}-sg-config.json not found!")
        
        if not data_filepath.exists():
            raise FileNotFoundError(f"Data file {dataset_name}-sg.json not found!")
        
        with open(config_filepath, encoding="utf-8") as fin:
            dataset_config = cast(dict, load(fin))
            if not isinstance(dataset_config, dict):
                raise ValueError(f"Badly formatted {dataset_name}-sg-config.json (not an object)")
            
        users = _get_typed_required(dataset_config, "users", dict)
        
        db_payload: PutDatabasePayload = PutDatabasePayload(dataset_config)
        try:
            self.__couchbase_server.create_bucket(db_payload.bucket)
            self._create_collections(db_payload)
            await self.__sync_gateway.put_database(dataset_name, db_payload)
        except CblSyncGatewayBadResponseError as e:
            if e.code != 412:
                raise

            await self.__sync_gateway.delete_database(dataset_name)
            self.__couchbase_server.drop_bucket(db_payload.bucket)
            self.__couchbase_server.create_bucket(db_payload.bucket)
            self._create_collections(db_payload)
            await self.__sync_gateway.put_database(dataset_name, db_payload)

        for user in users:
            user_dict = _get_typed_required(users, user, dict)
            await self.__sync_gateway.add_user(dataset_name, user, user_dict["password"], user_dict["collection_access"])

        await self.__sync_gateway.load_dataset(dataset_name, data_filepath)