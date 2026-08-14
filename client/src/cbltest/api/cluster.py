from collections.abc import Sequence
from json import dumps, loads
from pathlib import Path
from typing import cast

import aiofiles
from opentelemetry.trace import get_tracer

from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.error import CblSyncGatewayBadResponseError, CblTestError
from cbltest.api.syncgateway import DatabaseConfig, SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.assertions import _assert_not_null
from cbltest.jsonhelper import _get_typed_required
from cbltest.utils import _try_n_times
from cbltest.version import VERSION


class CouchbaseCluster:
    """
    A class that represents a logical grouping of Sync Gateways and Couchbase Server nodes
    that function together as a cluster.  This requires optional information in the config
    JSON file to describe, and if that information is absent every cloud node will be in the
    same cluster.
    """

    @property
    def sync_gateway_cluster(self) -> SyncGatewayCluster:
        """A `SyncGatewayCluster` view over all Sync Gateway nodes managed by this instance."""
        return self.__sync_gateway_cluster

    @property
    def sync_gateways(self) -> Sequence[SyncGateway]:
        return self.sync_gateway_cluster.sync_gateways

    @property
    def couchbase_servers(self) -> Sequence[CouchbaseServer]:
        return self.__couchbase_servers

    def __init__(
        self,
        sync_gateways: Sequence[SyncGateway],
        servers: Sequence[CouchbaseServer],
    ):
        self.__sync_gateway_cluster = SyncGatewayCluster(sync_gateways)
        self.__couchbase_servers: Sequence[CouchbaseServer] = []
        if len(servers) > 0:
            self.__couchbase_servers = servers
        elif len(sync_gateways) > 1:
            raise CblTestError(
                "At least one Couchbase Server must be provided when configuring multiple Sync Gateway nodes"
            )
        elif not sync_gateways[0].using_rosmar:
            raise CblTestError("Couchbase Server must be provided if Sync Gateway is not using Rosmar")

        self.__tracer = get_tracer(__name__, VERSION)

    async def close(self) -> None:
        """Closes all the resources in the cluster"""
        for sgw in self.sync_gateways:
            await sgw.close()

    def _create_collections(self, db_payload: DatabaseConfig) -> None:
        if self.sync_gateways[0].using_rosmar:
            return
        assert db_payload.bucket is not None, "DatabaseConfig is missing required field 'bucket'"
        if db_payload.scopes:
            for scope, scope_config in db_payload.scopes.items():
                collections: list[str] = []
                if scope_config.collections:
                    if isinstance(scope_config.collections, dict):
                        collections = list(scope_config.collections.keys())
                    elif isinstance(scope_config.collections, list):
                        collections = scope_config.collections
                self.couchbase_servers[0].create_collections(db_payload.bucket, scope, collections)

    def _check_all_indexes_removed(self, bucket: str) -> None:
        count = self.couchbase_servers[0].indexes_count(bucket)
        if count > 0:
            raise ValueError(f"{count} indexes remain in '{bucket}' bucket")

    def _wait_for_all_indexed_removed(self, bucket: str) -> None:
        _try_n_times(10, 2, True, self._check_all_indexes_removed, bucket)

    async def configure_dataset(
        self,
        dataset_path: Path,
        dataset_name: str,
        sg_config_options: list[str] | None = None,
    ) -> None:
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
        with self.__tracer.start_as_current_span(
            "configure_dataset", attributes={"cbl.dataset.name": dataset_name}
        ) as current_span:
            _assert_not_null(dataset_path, "dataset_path")
            _assert_not_null(dataset_name, "dataset_name")

            config_filepath = dataset_path / f"{dataset_name}-sg-config.json"
            data_filepath = dataset_path / f"{dataset_name}-sg.json"
            if not config_filepath.exists():
                raise FileNotFoundError(f"Configuration file {dataset_name}-sg-config.json not found!")

            if not data_filepath.exists():
                raise FileNotFoundError(f"Data file {dataset_name}-sg.json not found!")

            async with aiofiles.open(config_filepath, encoding="utf-8") as fin:
                dataset_config = cast(dict, loads(await fin.read()))
                if not isinstance(dataset_config, dict):
                    raise ValueError(f"Badly formatted {dataset_name}-sg-config.json (not an object)")

            users = _get_typed_required(dataset_config, "users", dict)
            if sg_config_options is not None:
                nested_config = _get_typed_required(dataset_config, "config", dict)
                valid_options = _get_typed_required(dataset_config, "config_options", dict)

                for option in sg_config_options:
                    if option not in valid_options:
                        raise CblTestError(
                            f"{option} is not a valid option for {dataset_name} (valid options are {dumps([str(k) for k in valid_options])})"
                        )

                    addition = _get_typed_required(valid_options, option, dict)
                    for k in addition:
                        nested_config[k] = addition[k]

            db_payload: DatabaseConfig = DatabaseConfig.model_validate(dataset_config["config"])
            assert db_payload.bucket is not None, (
                f"{dataset_name}-sg-config.json config is missing required field 'bucket'"
            )
            sg = self.sync_gateways[0]
            try:
                # buckets and collections are implicitly created when using Rosmar
                if not sg.using_rosmar:
                    self.couchbase_servers[0].create_bucket(db_payload.bucket)
                    self._create_collections(db_payload)
                await sg.put_database(dataset_name, db_payload)
            except CblSyncGatewayBadResponseError as e:
                if e.code != 412:
                    raise

                current_span.add_event("Handle HTTP 412")
                await sg.delete_database(dataset_name)
                await self.drop_bucket(db_payload.bucket)
                await self.sync_gateway_cluster.wait_for_no_databases(db_payload.bucket)
                if not sg.using_rosmar:
                    self.couchbase_servers[0].create_bucket(db_payload.bucket)
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

                await sg.put_database(dataset_name, db_payload)

            for user in users:
                user_dict = _get_typed_required(users, user, dict)
                await sg.add_user(
                    dataset_name,
                    user,
                    user_dict["password"],
                    user_dict["collection_access"],
                )

            await sg.load_dataset(dataset_name, data_filepath)

            if len(self.sync_gateways) > 1:
                await self.sync_gateway_cluster.wait_for_db_online(dataset_name)

    async def drop_bucket(self, bucket_name: str) -> None:
        """Drop the bucket from the backing cluster."""
        sg = self.sync_gateways[0]
        if sg.using_rosmar:
            try:
                await sg._send_request("delete", f"/_rosmar/{bucket_name}")
            except CblSyncGatewayBadResponseError as e:
                if e.code != 404:
                    raise
        else:
            self.couchbase_servers[0].drop_bucket(bucket_name)
