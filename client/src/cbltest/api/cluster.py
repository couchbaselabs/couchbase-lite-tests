from collections.abc import Sequence
from json import dumps, loads
from pathlib import Path
from typing import cast

import aiofiles
from opentelemetry.trace import get_tracer

from cbltest.api.couchbaseserver import CouchbaseServer
from cbltest.api.error import CblTestError
from cbltest.api.syncgateway import DatabaseConfig, SyncGateway
from cbltest.api.syncgatewaycluster import SyncGatewayCluster
from cbltest.assertions import _assert_not_null
from cbltest.jsonhelper import _get_typed_required
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
    ) -> None:
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
        for cbs in self.couchbase_servers:
            await cbs.close()

    async def create_collections(self, db_payload: DatabaseConfig) -> None:
        """
        Create every scope and collection that the given database config refers to.

        No-ops when using Rosmar, where collections are created implicitly.

        :param db_payload: The database config naming the bucket, scopes and collections
        """
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
                await self.couchbase_servers[0].create_collections(db_payload.bucket, scope, collections)

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
        with self.__tracer.start_as_current_span("configure_dataset", attributes={"cbl.dataset.name": dataset_name}):
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
            await self.create_database(dataset_name, db_payload)
            sg = self.sync_gateways[0]

            for user in users:
                user_dict = _get_typed_required(users, user, dict)
                await sg.add_user(
                    dataset_name,
                    user,
                    user_dict["password"],
                    user_dict["collection_access"],
                )

            await sg.load_dataset(dataset_name, data_filepath)
        await self.sync_gateway_cluster.wait_for_db_online(dataset_name)

    async def create_database(self, db_name: str, config: DatabaseConfig, *, bucket_replicas: int = 0) -> None:
        """
        Create the backing bucket and collections for a database, then create the
        database itself on the Sync Gateway cluster.

        :param db_name: The name of the database to create
        :param config: The configuration of the database to create
        :param bucket_replicas: The number of replicas for the backing bucket (default 0)
        """
        # buckets and collections are implicitly created when using Rosmar
        if not self.sync_gateways[0].using_rosmar:
            assert config.bucket, "bucket needs to be specified in a database config"
            bucket_created = await self.couchbase_servers[0].create_bucket(config.bucket, num_replicas=bucket_replicas)
            await self.create_collections(config)
            # Stale indexes only linger from a previous incarnation of the bucket, so
            # this is only worth waiting on when we just recreated it.
            if bucket_created:
                await self.couchbase_servers[0].wait_for_indexes_removed(config.bucket)
        await self.sync_gateway_cluster.create_database(db_name, config)
