from json import dumps

from .api.couchbaseserver import CouchbaseServer
from .api.edgeserver import EdgeServer
from .api.syncgateway import SyncGateway
from .api.testserver import TestServer
from .assertions import _assert_not_null
from .configparser import (
    CouchbaseServerInfo,
    EdgeServerInfo,
    ParsedConfig,
    SyncGatewayInfo,
    TestServerInfo,
    _parse_config,
)
from .extrapropsparser import _parse_extra_props
from .globals import CBLPyTestGlobal
from .logging import LogLevel, cbl_log_init, cbl_setLogLevel
from .requests import RequestFactory
from .version import available_api_version


class CBLPyTest:
    """
    This is the top level class that users will interact with when using this test client SDK.  For the moment,
    it parsed the passed configuration and creates an appropriate request factory
    """

    @property
    def config(self) -> ParsedConfig:
        """Gets the config as parsed from the provided JSON file path"""
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
    def test_servers(self) -> list[TestServer]:
        """Gets the list of Test Servers available"""
        return self.__test_servers

    @property
    def sync_gateways(self) -> list[SyncGateway]:
        """Gets the list of Sync Gateways available"""
        return self.__sync_gateways

    @property
    def couchbase_servers(self) -> list[CouchbaseServer]:
        """Gets the list of Couchbase Servers available"""
        return self.__couchbase_servers

    @property
    def edge_servers(self) -> list[EdgeServer]:
        """Gets the list of Edge Servers available"""
        return self.__edge_servers

    @property
    def load_balancers(self) -> list[str]:
        """Gets the list of Load Balancers available"""
        return self.__config.load_balancers

    @staticmethod
    async def create(
        config_path: str,
        log_level: LogLevel = LogLevel.VERBOSE,
        extra_props_path: str | None = None,
        test_server_only: bool = False,
        dataset_version: str = "4.0",
    ):
        ret_val = CBLPyTest(
            config_path, log_level, extra_props_path, test_server_only, dataset_version
        )
        if not ret_val.extra_props.get("auto_start_tdk_page", True):
            CBLPyTestGlobal.auto_start_tdk_page = False

        await ret_val.request_factory.start()
        cbl_log_init(str(ret_val.request_factory.uuid), ret_val.config.logslurp_url)

        ts_index = 0
        await ret_val.resolve_api_version()
        for ts in ret_val.test_servers:
            await ts.new_session(
                str(ret_val.request_factory.uuid),
                ret_val.config.logslurp_url,
                f"test-server[{ts_index}]",
            )
            ts_index += 1

        return ret_val

    def __init__(
        self,
        config_path: str,
        log_level: LogLevel = LogLevel.VERBOSE,
        extra_props_path: str | None = None,
        test_server_only: bool = False,
        dataset_version: str = "4.0",
    ):
        _assert_not_null(config_path, "config_path")
        self.__config = _parse_config(config_path)
        self.__log_level = LogLevel(log_level)
        cbl_setLogLevel(self.__log_level)
        self.__extra_props = {}
        if extra_props_path is not None:
            self.__extra_props = _parse_extra_props(extra_props_path)

        self.__request_factory = RequestFactory(self.__config)
        self.__test_servers: list[TestServer] = []
        index = 0
        for ts in self.__config.test_servers:
            ts_info = TestServerInfo(ts)
            dataset_version = ts_info.dataset_version or dataset_version
            self.__test_servers.append(
                TestServer(self.__request_factory, index, ts_info.url, dataset_version)
            )
            index += 1

        self.__sync_gateways: list[SyncGateway] = []
        index = 0
        if not test_server_only:
            for sg in self.__config.sync_gateways:
                sgw_info = SyncGatewayInfo(sg)
                self.__sync_gateways.append(
                    SyncGateway(
                        sgw_info.hostname,
                        sgw_info.rbac_user,
                        sgw_info.rbac_password,
                        sgw_info.admin_port,
                        sgw_info.uses_tls,
                    )
                )
                index += 1

        self.__couchbase_servers: list[CouchbaseServer] = []
        if not test_server_only:
            for cbs in self.__config.couchbase_servers:
                cbs_info = CouchbaseServerInfo(cbs)
                self.__couchbase_servers.append(
                    CouchbaseServer(
                        cbs_info.hostname, cbs_info.admin_user, cbs_info.admin_password
                    )
                )
        self.__edge_servers: list[EdgeServer] = []
        if not test_server_only:
            for es in self.__config.edge_servers:
                es_info = EdgeServerInfo(es)
                self.__edge_servers.append(EdgeServer(es_info.hostname))

        self.__edge_servers: list[EdgeServer] = []
        if not test_server_only:
            for es in self.__config.edge_servers:
                es_info = EdgeServerInfo(es)
                self.__edge_servers.append(EdgeServer(es_info.hostname))

    async def resolve_api_version(self) -> None:
        ts_index = 0
        apiVersion = 0
        for ts in self.test_servers:
            root_info = await ts.get_info()
            if apiVersion != 0 and root_info.version != apiVersion:
                raise ValueError(
                    f"Test Server at index {ts_index} has API version "
                    f"{root_info.version} which does not match other test servers' "
                    f"API version {apiVersion}"
                )

            apiVersion = available_api_version(root_info.version)
            ts_index += 1

        self.__request_factory.version = apiVersion

    async def close(self) -> None:
        """
        Closes all the test servers and sync gateways
        """
        await self.request_factory.close()
        for sg in self.__sync_gateways:
            await sg.close()

    def __str__(self) -> str:
        ret_val = (
            "Configuration:"
            + "\n"
            + str(self.__config)
            + "\n\n"
            + "Log Level: "
            + str(self.__log_level)
        )

        if self.__extra_props is not None:
            ret_val += "\n" + "Extra Properties:" + "\n" + dumps(self.__extra_props)

        return ret_val
