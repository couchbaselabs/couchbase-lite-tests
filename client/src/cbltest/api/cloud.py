from json import dumps, load
from pathlib import Path
from typing import List, Optional, cast

from opentelemetry.trace import get_tracer
from varname import nameof

from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.error import CblSyncGatewayBadResponseError, CblTestError
from cbltest.api.syncgateway import PutDatabasePayload, SyncGateway
from cbltest.assertions import _assert_not_null
from cbltest.jsonhelper import _get_typed_required
from cbltest.utils import _try_n_times
from cbltest.version import VERSION


class CouchbaseCloud:
    """
    A class that performs operations that require coordination between both Sync Gateway and Couchbase Server
    """

    def __init__(self, sync_gateway: SyncGateway, server: CouchbaseServer):
        self.__sync_gateway = sync_gateway
        self.__couchbase_server = server
        self.__tracer = get_tracer(__name__, VERSION)

    def _create_collections(self, db_payload: PutDatabasePayload) -> None:
        for scope in db_payload.scopes():
            self.__couchbase_server.create_collections(db_payload.bucket, scope, db_payload.collections(scope))

    def _check_all_indexes_removed(self, bucket: str) -> None:
        count = self.__couchbase_server.indexes_count(bucket)
        if count > 0:
            raise ValueError(f"{count} indexes remain in '{bucket}' bucket")

    def _wait_for_all_indexed_removed(self, bucket: str) -> None:
        _try_n_times(10, 2, True, self._check_all_indexes_removed, type(None), bucket)

    async def create_role(self, db_name: str, role: str, collection_access: dict) -> None:
        await self.__sync_gateway.add_role(db_name, role, collection_access)

    async def configure_dataset(self, dataset_path: Path, dataset_name: str,
                                sg_config_options: Optional[List[str]] = None) -> None:
        """
        Creates a database, ensuring that it is in an empty state when finished

        :param dataset_path: The path to the folder containing the configuration data
        :param dataset_name: The name of the dataset configuration to use
        :param sg_config_options: An optional list of options to apply to the base SG config
        
        .. note:: The expected format is a file named <database_name>-sg-config.json
                  containing a config and users key, for use with the PUT /<db> and
                  PUT /<db>/<user> endpoints and a file named <database_name>-sg.json
                  containing the actual data to populate.  Any config options that can
                  be passed to sg_config_options will be in a key called "config_options"
                  in <database_name>-sg-config.json
        """
        with self.__tracer.start_as_current_span("configure_dataset",
                                                 attributes={"cbl.dataset.name": dataset_name}) as current_span:
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
            if sg_config_options is not None:
                nested_config = _get_typed_required(dataset_config, "config", dict)
                valid_options = _get_typed_required(dataset_config, "config_options", dict)

                for option in sg_config_options:
                    if option not in valid_options:
                        raise CblTestError(
                            f"{option} is not a valid option for {dataset_name} (valid options are {dumps(list(str(k) for k in valid_options.keys()))})")

                    addition = _get_typed_required(valid_options, option, dict)
                    for k in addition:
                        nested_config[k] = addition[k]

            db_payload: PutDatabasePayload = PutDatabasePayload(dataset_config)
            try:
                self.__couchbase_server.create_bucket(db_payload.bucket)
                self._create_collections(db_payload)
                await self.__sync_gateway.put_database(dataset_name, db_payload)
            except CblSyncGatewayBadResponseError as e:
                if e.code != 412:
                    raise

                current_span.add_event("Handle HTTP 412")
                await self.__sync_gateway.delete_database(dataset_name)
                self.__couchbase_server.drop_bucket(db_payload.bucket)
                self.__couchbase_server.create_bucket(db_payload.bucket)
                self._create_collections(db_payload)

                # CBL-4977 :
                # The bucket's indexes will be deleted asynchronously after the bucket is dropped.
                # When recreating the sg database, sg may wrongly detect that the indexes already exist,
                # but later when trying to use the indexes for querying, the index-not-available error occurs
                # as the index has already been deleted by that time.
                #
                # Wait until all indexes are removed will help prevent that problem. It's important
                # to wait after the bucket and its collections are created, otherwise, QueryIndexManager
                # will not be able to return the pending-to-removed indexes created for the collections.
                self._wait_for_all_indexed_removed(db_payload.bucket)

                await self.__sync_gateway.put_database(dataset_name, db_payload)

            for user in users:
                user_dict = _get_typed_required(users, user, dict)
                await self.__sync_gateway.add_user(dataset_name, user, user_dict["password"],
                                                   user_dict["collection_access"])

            await self.__sync_gateway.load_dataset(dataset_name, data_filepath)
