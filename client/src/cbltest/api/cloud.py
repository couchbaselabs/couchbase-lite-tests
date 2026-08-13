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


class CouchbaseCloud:
    """
    A class that performs operations that require coordination between both Sync Gateway
    and Couchbase Server.
    """

    def __init__(
        self,
        sync_gateways: list[SyncGateway],
        server: CouchbaseServer | None,
    ):
        if not sync_gateways:
            raise CblTestError("At least one Sync Gateway must be provided")
        self.__sync_gateways = sync_gateways
        self.__sync_gateway_cluster = SyncGatewayCluster(sync_gateways)

        if server:
            self.__couchbase_server: CouchbaseServer = server
        elif len(self.__sync_gateways) > 1:
            raise CblTestError("Couchbase Server must be provided when configuring multiple Sync Gateway nodes")
        elif not self.__sync_gateways[0].using_rosmar:
            raise CblTestError("Couchbase Server must be provided if Sync Gateway is not using Rosmar")
        self.__tracer = get_tracer(__name__, VERSION)

    @property
    def sync_gateways(self) -> list[SyncGateway]:
        """All Sync Gateway nodes managed by this Couchbase Cloud instance."""
        return self.__sync_gateways

    @property
    def sync_gateway_cluster(self) -> SyncGatewayCluster:
        """A `SyncGatewayCluster` view over all Sync Gateway nodes managed by this instance."""
        return self.__sync_gateway_cluster

    @property
    def couchbase_server(self) -> CouchbaseServer:
        if not hasattr(self, "_CouchbaseCloud__couchbase_server"):
            raise CblTestError(
                "Couchbase Server is not available for this Couchbase Cloud instance, configured using rosmar"
            )
        return self.__couchbase_server

    def _create_collections(self, db_payload: DatabaseConfig) -> None:
        if self.__sync_gateways[0].using_rosmar:
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
                self.__couchbase_server.create_collections(db_payload.bucket, scope, collections)

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
            sg = self.__sync_gateways[0]
            # buckets and collections are implicitly created when using Rosmar
            if not sg.using_rosmar:
                self.couchbase_server.create_bucket(db_payload.bucket)
                self._create_collections(db_payload)
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

            if len(self.__sync_gateways) > 1:
                await self.sync_gateway_cluster.wait_for_db_online(dataset_name)
