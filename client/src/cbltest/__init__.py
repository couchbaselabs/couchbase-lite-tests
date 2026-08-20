from collections.abc import Sequence
from json import dumps

from cbltest.api.error import CblTestError

from .api.cluster import CouchbaseCluster
from .api.couchbaseserver import CouchbaseServer
from .api.edgeserver import EdgeServer
from .api.syncgateway import SyncGateway
from .api.syncgatewaycluster import SyncGatewayCluster
from .api.testserver import TestServer
from .configparser import (
    CouchbaseServerInfo,
    EdgeServerInfo,
    ParsedConfig,
    SyncGatewayInfo,
    TestServerInfo,
)
from .extrapropsparser import _parse_extra_props
from .globals import CBLPyTestGlobal
from .logging import LogLevel, cbl_log_init, cbl_setLogLevel
from .requests import RequestFactory
from .version import available_api_version


class _ClusterBuilder:
    def __init__(self) -> None:
        # These may come in from the config file out of order,
        # so use dictionaries to collect them instead of hacking
        # None or blank clusters into a list
        self.__sgw: dict[int, list[SyncGateway]] = {}
        self.__cbs: dict[int, list[CouchbaseServer]] = {}

    def add_entry(self, entry: SyncGateway | CouchbaseServer, idx: int) -> None:
        if isinstance(entry, SyncGateway):
            self.__sgw.setdefault(idx, []).append(entry)
        else:
            self.__cbs.setdefault(idx, []).append(entry)

    def build(self) -> Sequence[CouchbaseCluster]:
        self._validate()
        ret_val = []

        # Sync Gateway is at least as long as CBS
        for idx in range(len(self.__sgw)):
            servers = [] if idx >= len(self.__cbs) else self.__cbs[idx]
            sync_gateways = self.__sgw[idx]
            ret_val.append(CouchbaseCluster(sync_gateways, servers))

        return ret_val

    def _validate(self) -> None:
        if len(self.__sgw) < len(self.__cbs):
            raise CblTestError("Every cluster should at least have one Sync Gateway")

        for name, d in (("sgw", self.__sgw), ("cbs", self.__cbs)):
            expected = set(range(len(d)))
            missing = expected - d.keys()
            if missing:
                raise CblTestError(
                    f"Cluster indices for {name} must start from 0 and be contiguous, missing: {sorted(missing)}"
                )


class CBLPyTest:
    """
    This is the top level class that users will interact with when using this test client SDK.  For the moment,
    it parsed the passed configuration and creates an appropriate request factory
    """

    @property
    def config(self) -> ParsedConfig:
        """Gets the config that was provided"""
        return self.__config

    @property
    def log_level(self) -> LogLevel:
        """Gets the log level provided"""
        return self.__log_level

    @property
    def extra_props(self) -> dict[str, str]:
        """Gets the extra properties provided as parsed from the provided JSON file path"""
        return self.__extra_props

    @property
    def request_factory(self) -> RequestFactory:
        """Gets the request factory for creating and sending requests to the test server"""
        return self.__request_factory

    @property
    def test_servers(self) -> Sequence[TestServer]:
        """Gets the list of Test Servers available"""
        return self.__test_servers

    @property
    def clusters(self) -> Sequence[CouchbaseCluster]:
        """Gets the list of Couchbase Cluster objects available"""
        return self.__clusters

    @property
    def sync_gateways(self) -> Sequence[SyncGateway]:
        """Gets the list of Sync Gateways available in the first cluster"""
        return self.clusters[0].sync_gateways if self.clusters else []

    @property
    def sync_gateway_cluster(self) -> SyncGatewayCluster:
        """Gets the Sync Gateway cluster view of the first cluster"""
        return self.clusters[0].sync_gateway_cluster

    @property
    def couchbase_servers(self) -> Sequence[CouchbaseServer]:
        """Gets the list of Couchbase Servers available in the first cluster"""
        return self.clusters[0].couchbase_servers if self.clusters else []

    @property
    def edge_servers(self) -> Sequence[EdgeServer]:
        """Gets the list of Edge Servers available"""
        return self.__edge_servers

    @property
    def load_balancers(self) -> Sequence[str]:
        """Gets the list of Load Balancers available"""
        return self.__config.load_balancers

    @staticmethod
    async def create(
        config: ParsedConfig,
        log_level: LogLevel = LogLevel.VERBOSE,
        extra_props_path: str | None = None,
        test_server_only: bool = False,
        dataset_version: str = "4.0",
    ) -> "CBLPyTest":
        ret_val = CBLPyTest(config, log_level, extra_props_path, test_server_only, dataset_version)
        if not ret_val.extra_props.get("auto_start_tdk_page", True):
            CBLPyTestGlobal.auto_start_tdk_page = False

        await ret_val.request_factory.start()
        cbl_log_init(str(ret_val.request_factory.uuid), ret_val.config.logslurp_url)

        await ret_val.resolve_api_version()
        for ts_index, ts in enumerate(ret_val.test_servers):
            await ts.new_session(
                str(ret_val.request_factory.uuid),
                ret_val.config.logslurp_url,
                f"test-server[{ts_index}]",
            )

        return ret_val

    def __init__(
        self,
        config: ParsedConfig,
        log_level: LogLevel = LogLevel.VERBOSE,
        extra_props_path: str | None = None,
        test_server_only: bool = False,
        dataset_version: str = "4.0",
    ) -> None:
        self.__config = config
        self.__log_level = LogLevel(log_level)
        cbl_setLogLevel(self.__log_level)
        self.__extra_props = {}
        if extra_props_path is not None:
            self.__extra_props = _parse_extra_props(extra_props_path)

        self.__request_factory = RequestFactory(self.__config)
        self.__test_servers: list[TestServer] = []
        for index, ts in enumerate(self.__config.test_servers):
            ts_info = TestServerInfo(ts)
            dataset_version = ts_info.dataset_version or dataset_version
            self.__test_servers.append(TestServer(self.__request_factory, index, ts_info.url, dataset_version))

        cluster_builder = _ClusterBuilder()
        if not test_server_only:
            for sg in self.__config.sync_gateways:
                sgw_info = SyncGatewayInfo(sg)
                cluster_builder.add_entry(
                    SyncGateway(
                        sgw_info.hostname,
                        sgw_info.rbac_user,
                        sgw_info.rbac_password,
                        sgw_info.admin_port,
                        sgw_info.uses_tls,
                    ),
                    sgw_info.cluster_index,
                )

        if not test_server_only:
            for cbs in self.__config.couchbase_servers:
                cbs_info = CouchbaseServerInfo(cbs)
                cluster_builder.add_entry(
                    CouchbaseServer(cbs_info.hostname, cbs_info.admin_user, cbs_info.admin_password),
                    cbs_info.cluster_index,
                )

        self.__clusters = cluster_builder.build()

        self.__edge_servers: list[EdgeServer] = []
        if not test_server_only:
            for es in self.__config.edge_servers:
                es_info = EdgeServerInfo(es)
                self.__edge_servers.append(
                    EdgeServer(
                        es_info.hostname,
                        es_info.admin_user,
                        es_info.admin_password,
                        es_info.config_path,
                    )
                )

    async def resolve_api_version(self) -> None:
        apiVersion = 0
        for ts_index, ts in enumerate(self.test_servers):
            root_info = await ts.get_info()
            if apiVersion != 0 and root_info.version != apiVersion:
                raise ValueError(
                    f"Test Server at index {ts_index} has API version "
                    f"{root_info.version} which does not match other test servers' "
                    f"API version {apiVersion}"
                )

            apiVersion = available_api_version(root_info.version)

        self.__request_factory.version = apiVersion

    async def close(self) -> None:
        """
        Closes all the clusters
        """
        await self.request_factory.close()
        for cluster in self.__clusters:
            await cluster.close()

    def __str__(self) -> str:
        ret_val = "Configuration:" + "\n" + str(self.__config) + "\n\n" + "Log Level: " + str(self.__log_level)

        if self.__extra_props is not None:
            ret_val += "\n" + "Extra Properties:" + "\n" + dumps(self.__extra_props)

        return ret_val
